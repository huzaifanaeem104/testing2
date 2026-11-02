# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import fields, _
from odoo.tools import SQL, Query
from odoo.tools.float_utils import float_is_zero

from .cash_flow_structure import CASH_FLOW_LAYOUT, CASH_FLOW_ROOT_ORDER


class CashFlowEngine:
    """Direct-method cash flow engine mirroring Odoo Enterprise account_reports."""

    def __init__(self, env, options):
        self.env = env
        self.company = env.company
        self.currency = self.company.currency_id
        self.options = options
        self.date_from = (
            fields.Date.to_date(options['date_from'])
            if options.get('date_from') else None
        )
        self.date_to = fields.Date.to_date(options['date_to'])
        self._company_ids = tuple(
            env['res.company'].search([('id', 'child_of', self.company.id)]).ids
        )

    def get_report_data(self):
        layout_data = self._layout_data()
        report_data = self._get_report_data(layout_data)
        lines = []
        for layout_id in CASH_FLOW_ROOT_ORDER:
            line = self._build_layout_line(layout_id, layout_data, report_data)
            if line:
                lines.append(line)

        unexplained = self._unexplained_difference(report_data)
        if unexplained:
            lines.append(unexplained)

        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'warnings': self._get_warnings(),
        }

    def flatten_lines(self, lines=None, unfolded_ids=None):
        unfolded_ids = set(unfolded_ids or [])
        unfold_all = self.options.get('unfold_all', True)
        result = []

        def _walk(node):
            result.append({k: v for k, v in node.items() if k != 'children'})
            children = node.get('children') or []
            if not children:
                return
            if unfold_all or node.get('id') in unfolded_ids or not node.get('foldable'):
                for child in children:
                    _walk(child)

        for line in lines or []:
            _walk(line)
        return result

    def _layout_data(self):
        return {
            key: {
                **meta,
                'name': meta['name'](self.env) if callable(meta['name']) else meta['name'],
            }
            for key, meta in CASH_FLOW_LAYOUT.items()
        }

    def _get_date_bounds(self, date_scope):
        date_to = self.date_to
        date_from = self.date_from
        if date_scope == 'to_beginning_of_period':
            eve = (date_from or date_to) - relativedelta(days=1)
            return None, eve
        return date_from, date_to

    def _get_date_label(self):
        if self.date_from:
            if (
                self.date_from.day == 1
                and self.date_to == self.date_from + relativedelta(months=1, days=-1)
            ):
                return self.date_from.strftime('%b %Y')
            return (
                f"{fields.Date.to_string(self.date_from)} — "
                f"{fields.Date.to_string(self.date_to)}"
            )
        return fields.Date.to_string(self.date_to)

    def _get_warnings(self):
        warnings = []
        if self.options.get('target_move') == 'posted':
            domain = [
                ('company_id', 'child_of', self.company.id),
                ('state', '=', 'draft'),
                ('date', '<=', self.date_to),
            ]
            if self.date_from:
                domain.append(('date', '>=', self.date_from))
            if self.env['account.move'].search_count(domain, limit=1):
                warnings.append(
                    _('There are unposted Journal Entries prior or included in this period.')
                )
        return warnings

    def _aml_state_clause(self):
        if self.options.get('target_move') == 'posted':
            return SQL("account_move_line.parent_state = 'posted'")
        return SQL('TRUE')

    def _get_payment_account_ids(self):
        journal_ids = self.options.get('journal_ids') or []
        if journal_ids:
            where_clause = SQL('account_journal.id IN %s', tuple(journal_ids))
        else:
            where_clause = SQL("account_journal.type IN ('bank', 'cash', 'general')")

        self.env.cr.execute(SQL(
            '''
            SELECT
                array_remove(ARRAY_AGG(DISTINCT account_account.id), NULL),
                array_remove(ARRAY_AGG(DISTINCT account_payment_method_line.payment_account_id), NULL)
            FROM account_journal
            JOIN res_company ON account_journal.company_id = res_company.id
            LEFT JOIN account_payment_method_line
                ON account_journal.id = account_payment_method_line.journal_id
            LEFT JOIN account_account
                ON account_journal.default_account_id = account_account.id
                   AND account_account.account_type IN ('asset_cash', 'liability_credit_card')
            WHERE %(where_clause)s
                AND account_journal.company_id IN %(company_ids)s
            ''',
            where_clause=where_clause,
            company_ids=self._company_ids,
        ))
        res = self.env.cr.fetchall()[0]
        payment_account_ids = set((res[0] or []) + (res[1] or []))
        return tuple(payment_account_ids)

    def _compute_liquidity_balance(self, payment_account_ids, date_scope):
        if not payment_account_ids:
            return []

        date_from, date_to = self._get_date_bounds(date_scope)
        date_clauses = [SQL('account_move_line.date <= %(date_to)s', date_to=date_to)]
        if date_from:
            date_clauses.append(SQL('account_move_line.date >= %(date_from)s', date_from=date_from))

        query = Query(self.env, 'account_move_line')
        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id',
        )
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)

        self.env.cr.execute(SQL(
            '''
            SELECT
                account_move_line.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                SUM(account_move_line.balance) AS balance
            FROM %(from_clause)s
            WHERE account_move_line.company_id IN %(company_ids)s
                AND account_move_line.account_id IN %(payment_account_ids)s
                AND account_move_line.display_type NOT IN ('line_section', 'line_note')
                AND %(state_clause)s
                AND %(date_clauses)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s
            ''',
            account_code=account_code,
            account_name=account_name,
            from_clause=query.from_clause,
            company_ids=self._company_ids,
            payment_account_ids=payment_account_ids,
            state_clause=self._aml_state_clause(),
            date_clauses=SQL(' AND ').join(date_clauses),
        ))
        return self.env.cr.dictfetchall()

    def _get_move_ids_query(self, payment_account_ids):
        date_from, date_to = self._get_date_bounds('strict_range')
        date_clauses = [SQL('account_move_line.date <= %(date_to)s', date_to=date_to)]
        if date_from:
            date_clauses.append(SQL('account_move_line.date >= %(date_from)s', date_from=date_from))

        return SQL(
            '''
            SELECT array_agg(DISTINCT account_move_line.move_id) AS move_id
            FROM account_move_line
            WHERE account_move_line.company_id IN %(company_ids)s
                AND account_move_line.account_id IN %(payment_account_ids)s
                AND account_move_line.display_type NOT IN ('line_section', 'line_note')
                AND %(state_clause)s
                AND %(date_clauses)s
            ''',
            company_ids=self._company_ids,
            payment_account_ids=payment_account_ids,
            state_clause=self._aml_state_clause(),
            date_clauses=SQL(' AND ').join(date_clauses),
        )

    def _get_tags_ids(self):
        return {
            'operating': self.env.ref('account.account_tag_operating').id,
            'investing': self.env.ref('account.account_tag_investing').id,
            'financing': self.env.ref('account.account_tag_financing').id,
        }

    def _get_cashflow_tag_ids(self):
        return tuple(self._get_tags_ids().values())

    def _get_liquidity_moves(self, payment_account_ids, cashflow_tag_ids):
        reconciled_aml_groupby_account = {}
        move_ids_query = self._get_move_ids_query(payment_account_ids)
        date_from, date_to = self._get_date_bounds('strict_range')

        query = Query(self.env, 'account_move_line')
        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id',
        )
        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
        account_type = SQL.identifier(account_alias, 'account_type')

        self.env.cr.execute(SQL(
            '''
            (WITH payment_move_ids AS (%(move_ids_query)s)
            SELECT
                account_move_line.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_type)s AS account_account_type,
                account_account_account_tag.account_account_tag_id AS account_tag_id,
                SUM(account_partial_reconcile.amount) AS balance
            FROM %(from_clause)s
            LEFT JOIN account_partial_reconcile
                ON account_partial_reconcile.credit_move_id = account_move_line.id
            LEFT JOIN account_account_account_tag
                ON account_account_account_tag.account_account_id = account_move_line.account_id
                AND account_account_account_tag.account_account_tag_id IN %(cash_flow_tag_ids)s
            WHERE account_move_line.move_id IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND account_move_line.account_id NOT IN %(payment_account_ids)s
                AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s,
                account_account_type, account_account_account_tag.account_account_tag_id

            UNION ALL

            SELECT
                account_move_line.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_type)s AS account_account_type,
                account_account_account_tag.account_account_tag_id AS account_tag_id,
                -SUM(account_partial_reconcile.amount) AS balance
            FROM %(from_clause)s
            LEFT JOIN account_partial_reconcile
                ON account_partial_reconcile.debit_move_id = account_move_line.id
            LEFT JOIN account_account_account_tag
                ON account_account_account_tag.account_account_id = account_move_line.account_id
                AND account_account_account_tag.account_account_tag_id IN %(cash_flow_tag_ids)s
            WHERE account_move_line.move_id IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND account_move_line.account_id NOT IN %(payment_account_ids)s
                AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s,
                account_account_type, account_account_account_tag.account_account_tag_id

            UNION ALL

            SELECT
                account_move_line.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_type)s AS account_account_type,
                account_account_account_tag.account_account_tag_id AS account_tag_id,
                SUM(account_move_line.balance) AS balance
            FROM %(from_clause)s
            LEFT JOIN account_account_account_tag
                ON account_account_account_tag.account_account_id = account_move_line.account_id
                AND account_account_account_tag.account_account_tag_id IN %(cash_flow_tag_ids)s
            WHERE account_move_line.move_id IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND account_move_line.account_id NOT IN %(payment_account_ids)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s,
                account_account_type, account_account_account_tag.account_account_tag_id)
            ''',
            move_ids_query=move_ids_query,
            account_code=account_code,
            account_name=account_name,
            account_type=account_type,
            from_clause=query.from_clause,
            cash_flow_tag_ids=cashflow_tag_ids,
            payment_account_ids=payment_account_ids,
            date_from=date_from,
            date_to=date_to,
        ))

        for aml_data in self.env.cr.dictfetchall():
            reconciled_aml_groupby_account.setdefault(aml_data['account_id'], {
                'account_id': aml_data['account_id'],
                'account_code': aml_data['account_code'],
                'account_name': aml_data['account_name'],
                'account_account_type': aml_data['account_account_type'],
                'account_tag_id': aml_data['account_tag_id'],
                'balance': 0.0,
            })
            reconciled_aml_groupby_account[aml_data['account_id']]['balance'] -= aml_data['balance']

        return list(reconciled_aml_groupby_account.values())

    def _get_reconciled_moves(self, payment_account_ids, cashflow_tag_ids):
        move_ids_query = self._get_move_ids_query(payment_account_ids)
        date_from, date_to = self._get_date_bounds('strict_range')
        reconciled_percentage_per_move = {}
        reconciled_account_ids = set()

        self.env.cr.execute(SQL(
            '''
            (WITH payment_move_ids AS (%(move_ids_query)s)
            SELECT
                debit_line.move_id,
                debit_line.account_id,
                SUM(account_partial_reconcile.amount) AS balance
            FROM account_move_line AS credit_line
            LEFT JOIN account_partial_reconcile
                ON account_partial_reconcile.credit_move_id = credit_line.id
            INNER JOIN account_move_line AS debit_line
                ON debit_line.id = account_partial_reconcile.debit_move_id
            WHERE credit_line.move_id IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND credit_line.account_id NOT IN %(payment_account_ids)s
                AND credit_line.credit > 0.0
                AND debit_line.move_id NOT IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY debit_line.move_id, debit_line.account_id

            UNION ALL

            SELECT
                credit_line.move_id,
                credit_line.account_id,
                -SUM(account_partial_reconcile.amount) AS balance
            FROM account_move_line AS debit_line
            LEFT JOIN account_partial_reconcile
                ON account_partial_reconcile.debit_move_id = debit_line.id
            INNER JOIN account_move_line AS credit_line
                ON credit_line.id = account_partial_reconcile.credit_move_id
            WHERE debit_line.move_id IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND debit_line.account_id NOT IN %(payment_account_ids)s
                AND debit_line.debit > 0.0
                AND credit_line.move_id NOT IN (
                    SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids
                )
                AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY credit_line.move_id, credit_line.account_id)
            ''',
            move_ids_query=move_ids_query,
            payment_account_ids=payment_account_ids,
            date_from=date_from,
            date_to=date_to,
        ))

        for aml_data in self.env.cr.dictfetchall():
            reconciled_percentage_per_move.setdefault(aml_data['move_id'], {})
            reconciled_percentage_per_move[aml_data['move_id']].setdefault(
                aml_data['account_id'], [0.0, 0.0]
            )
            reconciled_percentage_per_move[aml_data['move_id']][aml_data['account_id']][0] += (
                aml_data['balance']
            )
            reconciled_account_ids.add(aml_data['account_id'])

        if not reconciled_percentage_per_move:
            return []

        move_ids = tuple(reconciled_percentage_per_move.keys())
        account_ids = tuple(reconciled_account_ids) or (None,)

        self.env.cr.execute(SQL(
            '''
            SELECT
                account_move_line.move_id,
                account_move_line.account_id,
                SUM(account_move_line.balance) AS balance
            FROM account_move_line
            WHERE account_move_line.move_id IN %(move_ids)s
                AND account_move_line.account_id IN %(account_ids)s
            GROUP BY account_move_line.move_id, account_move_line.account_id
            ''',
            move_ids=move_ids,
            account_ids=account_ids,
        ))

        for aml_data in self.env.cr.dictfetchall():
            move_map = reconciled_percentage_per_move.get(aml_data['move_id'], {})
            if aml_data['account_id'] in move_map:
                move_map[aml_data['account_id']][1] += aml_data['balance']

        query = Query(self.env, 'account_move_line')
        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id',
        )
        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
        account_type = SQL.identifier(account_alias, 'account_type')

        self.env.cr.execute(SQL(
            '''
            SELECT
                account_move_line.move_id,
                account_move_line.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_type)s AS account_account_type,
                account_account_account_tag.account_account_tag_id AS account_tag_id,
                SUM(account_move_line.balance) AS balance
            FROM %(from_clause)s
            LEFT JOIN account_account_account_tag
                ON account_account_account_tag.account_account_id = account_move_line.account_id
                AND account_account_account_tag.account_account_tag_id IN %(cash_flow_tag_ids)s
            WHERE account_move_line.move_id IN %(move_ids)s
            GROUP BY account_move_line.move_id, account_move_line.account_id,
                %(account_code)s, %(account_name)s, account_account_type,
                account_account_account_tag.account_account_tag_id
            ''',
            account_code=account_code,
            account_name=account_name,
            account_type=account_type,
            from_clause=query.from_clause,
            cash_flow_tag_ids=cashflow_tag_ids,
            move_ids=move_ids,
        ))

        reconciled_aml_per_account = {}
        for aml_data in self.env.cr.dictfetchall():
            move_id = aml_data['move_id']
            account_id = aml_data['account_id']
            aml_balance = aml_data['balance']
            move_accounts = reconciled_percentage_per_move.get(move_id, {})

            total_reconciled_amount = sum(v[0] for v in move_accounts.values())
            total_amount = sum(v[1] for v in move_accounts.values())

            if total_amount and account_id not in move_accounts:
                reconciled_percentage = total_reconciled_amount / total_amount
                aml_balance *= reconciled_percentage
            elif not total_amount and account_id in move_accounts:
                aml_balance = -move_accounts[account_id][0]
            else:
                continue

            bucket = reconciled_aml_per_account.setdefault(account_id, {
                'account_id': account_id,
                'account_code': aml_data['account_code'],
                'account_name': aml_data['account_name'],
                'account_account_type': aml_data['account_account_type'],
                'account_tag_id': aml_data['account_tag_id'],
                'balance': 0.0,
            })
            bucket['balance'] -= aml_balance

        return list(reconciled_aml_per_account.values())

    def _get_report_data(self, layout_data):
        report_data = {}
        payment_account_ids = self._get_payment_account_ids()
        if not payment_account_ids:
            return report_data

        for aml_data in self._compute_liquidity_balance(payment_account_ids, 'to_beginning_of_period'):
            self._add_report_data('opening_balance', aml_data, layout_data, report_data)
            self._add_report_data('closing_balance', aml_data, layout_data, report_data)

        for aml_data in self._compute_liquidity_balance(payment_account_ids, 'strict_range'):
            self._add_report_data('closing_balance', aml_data, layout_data, report_data)

        tags_ids = self._get_tags_ids()
        cashflow_tag_ids = self._get_cashflow_tag_ids()

        for aml_data in self._get_liquidity_moves(payment_account_ids, cashflow_tag_ids):
            self._dispatch_aml_data(tags_ids, aml_data, layout_data, report_data)

        for aml_data in self._get_reconciled_moves(payment_account_ids, cashflow_tag_ids):
            self._dispatch_aml_data(tags_ids, aml_data, layout_data, report_data)

        return report_data

    def _add_report_data(self, layout_line_id, aml_data, layout_data, report_data):
        def _update_parent(line_id, balance):
            parent_id = layout_data[line_id].get('parent_id')
            if not parent_id:
                return
            report_data.setdefault(parent_id, {'balance': 0.0, 'accounts': {}})
            report_data[parent_id]['balance'] += balance
            _update_parent(parent_id, balance)

        balance = aml_data['balance']
        if float_is_zero(balance, precision_rounding=self.currency.rounding):
            return

        report_data.setdefault(layout_line_id, {'balance': 0.0, 'accounts': {}})
        report_data[layout_line_id]['balance'] += balance

        account_id = aml_data['account_id']
        accounts = report_data[layout_line_id]['accounts']
        if account_id not in accounts:
            accounts[account_id] = {
                'account_id': account_id,
                'account_code': aml_data.get('account_code'),
                'account_name': aml_data.get('account_name'),
                'balance': 0.0,
                'level': layout_data[layout_line_id]['level'] + 1,
            }
        accounts[account_id]['balance'] += balance
        _update_parent(layout_line_id, balance)

    def _dispatch_aml_data(self, tags_ids, aml_data, layout_data, report_data):
        if aml_data['account_account_type'] == 'asset_receivable':
            self._add_report_data('advance_payments_customer', aml_data, layout_data, report_data)
        elif aml_data['account_account_type'] == 'liability_payable':
            self._add_report_data('advance_payments_suppliers', aml_data, layout_data, report_data)
        elif aml_data['balance'] < 0:
            tag_id = aml_data.get('account_tag_id')
            if tag_id == tags_ids['operating']:
                self._add_report_data('paid_operating_activities', aml_data, layout_data, report_data)
            elif tag_id == tags_ids['investing']:
                self._add_report_data('investing_activities_cash_out', aml_data, layout_data, report_data)
            elif tag_id == tags_ids['financing']:
                self._add_report_data('financing_activities_cash_out', aml_data, layout_data, report_data)
            else:
                self._add_report_data('unclassified_activities_cash_out', aml_data, layout_data, report_data)
        elif aml_data['balance'] > 0:
            tag_id = aml_data.get('account_tag_id')
            if tag_id == tags_ids['operating']:
                self._add_report_data('received_operating_activities', aml_data, layout_data, report_data)
            elif tag_id == tags_ids['investing']:
                self._add_report_data('investing_activities_cash_in', aml_data, layout_data, report_data)
            elif tag_id == tags_ids['financing']:
                self._add_report_data('financing_activities_cash_in', aml_data, layout_data, report_data)
            else:
                self._add_report_data('unclassified_activities_cash_in', aml_data, layout_data, report_data)

    def _build_layout_line(self, layout_id, layout_data, report_data):
        meta = layout_data[layout_id]
        data = report_data.get(layout_id, {})
        balance = data.get('balance', 0.0)
        accounts = data.get('accounts', {})

        account_children = []
        if accounts:
            sorted_accounts = sorted(
                accounts.values(),
                key=lambda row: row.get('account_code') or '',
            )
            for account in sorted_accounts:
                if float_is_zero(account['balance'], precision_rounding=self.currency.rounding):
                    continue
                name = account['account_name']
                if account.get('account_code'):
                    name = f"{account['account_code']} {account['account_name']}"
                account_children.append({
                    'id': f"{layout_id}_{account['account_id']}",
                    'name': name,
                    'level': account['level'],
                    'balance': account['balance'],
                    'foldable': False,
                    'line_type': 'account',
                    'account_id': account['account_id'],
                    'children': [],
                })

        child_layout_ids = meta.get('children') or []
        layout_children = [
            self._build_layout_line(child_id, layout_data, report_data)
            for child_id in child_layout_ids
        ]
        layout_children = [child for child in layout_children if child]
        children = layout_children + account_children

        return {
            'id': layout_id,
            'name': meta['name'],
            'level': meta['level'],
            'balance': balance,
            'foldable': bool(meta.get('foldable') and children),
            'line_type': meta.get('line_type', 'group'),
            'account_id': False,
            'children': children,
        }

    def _unexplained_difference(self, report_data):
        opening = report_data.get('opening_balance', {}).get('balance', 0.0)
        closing = report_data.get('closing_balance', {}).get('balance', 0.0)
        net = report_data.get('net_increase', {}).get('balance', 0.0)
        diff = closing - opening - net
        if float_is_zero(diff, precision_rounding=self.currency.rounding):
            return None
        return {
            'id': 'unexplained_difference',
            'name': _('Unexplained Difference'),
            'level': 1,
            'balance': diff,
            'foldable': False,
            'line_type': 'group',
            'account_id': False,
            'children': [],
        }

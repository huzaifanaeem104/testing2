# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields
from odoo.osv import expression
from odoo.tools.float_utils import float_is_zero

from .report_filter_domains import (
    analytic_reach_domain,
    exclude_ages_srb_wht_refund_domain,
    journal_reach_domain,
)


class GeneralLedgerEngine:
    """Enterprise-style General Ledger engine."""

    date_label_fields = ('date_from', 'date_to')

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

    def get_report_data(self):
        include_details = self.options.get('unfold_all', False)
        allowed = set(self.options['account_ids']) if self.options.get('account_ids') else None

        if include_details:
            period_lines = self._search_period_lines(allowed)
            self._prefetch_move_lines(period_lines)
            lines_by_account = self._group_lines_by_account(period_lines)
            period_totals = self._sum_line_groups(lines_by_account)
        else:
            period_totals = self._read_group_by_account('period', allowed)
            lines_by_account = {}

        initial_totals = self._initial_totals_by_account(allowed)
        account_ids = self._account_ids_from_totals(period_totals, initial_totals, allowed)
        accounts = self.env['account.account'].browse(account_ids).sorted(
            key=lambda acc: acc.code or ''
        )
        extra_by_account = self._batch_extra_children(accounts, lines_by_account, include_details)

        lines = []
        total_debit = total_credit = 0.0
        empty = self.env['account.move.line']
        for account in accounts:
            period = period_totals.get(account.id) or {
                'debit': 0.0, 'credit': 0.0, 'balance': 0.0,
            }
            account_line = self._build_account_line(
                account,
                include_details=include_details,
                move_lines=lines_by_account.get(account.id, empty) if include_details else empty,
                initial_balance=initial_totals.get(account.id, 0.0),
                extra_children=extra_by_account.get(account.id, []) if include_details else None,
                period_debit=period['debit'],
                period_credit=period['credit'],
                period_balance=period['balance'],
            )
            if account_line:
                lines.append(account_line)
                total_debit += account_line['debit']
                total_credit += account_line['credit']

        lines.append({
            'id': 'total',
            'name': 'Total',
            'level': 0,
            'line_type': 'total',
            'foldable': False,
            'account_id': False,
            'date': False,
            'communication': False,
            'partner_name': False,
            'amount_currency': False,
            'currency_name': False,
            'debit': total_debit,
            'credit': total_credit,
            'balance': self.currency.round(total_debit - total_credit),
            'children': [],
        })

        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'warnings': self._get_warnings(),
        }

    def get_account_detail(self, account_id):
        account = self.env['account.account'].browse(account_id)
        if not account.exists():
            return {'children': []}
        line = self._build_account_line(account, include_details=True)
        return {'children': line.get('children') or [] if line else []}

    def flatten_lines(self, lines=None, unfolded_ids=None):
        unfolded_ids = set(unfolded_ids or [])
        unfold_all = self.options.get('unfold_all', False)
        result = []

        def _walk(node):
            result.append({k: v for k, v in node.items() if k != 'children'})
            children = node.get('children') or []
            if not children:
                return
            show_children = (
                not node.get('foldable')
                or unfold_all
                or node.get('id') in unfolded_ids
            )
            if show_children:
                for child in children:
                    _walk(child)

        for line in lines or []:
            _walk(line)
        return result

    def _get_date_label(self):
        if self.date_from:
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
                    'There are unposted Journal Entries prior or included in this period.'
                )
        return warnings

    def _base_domain(self, date_scope='period', account_ids=None):
        domain = [
            ('company_id', 'child_of', self.company.id),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if self.options.get('target_move') == 'posted':
            domain.append(('parent_state', '=', 'posted'))

        if date_scope == 'period':
            if self.date_from:
                domain.append(('date', '>=', self.date_from))
            domain.append(('date', '<=', self.date_to))
        elif date_scope == 'before_period':
            if self.date_from:
                domain.append(('date', '<', self.date_from))
            else:
                domain.append(('date', '<=', self.date_to))
        elif date_scope == 'to_date':
            domain.append(('date', '<=', self.date_to))

        journal_domain = journal_reach_domain(self.env, self.options.get('journal_ids'))
        if journal_domain:
            domain = expression.AND([domain, journal_domain])

        analytic_domain = analytic_reach_domain(
            self.env, [self.options.get('analytic_account_id')]
        )
        if analytic_domain:
            domain = expression.AND([domain, analytic_domain])
        if account_ids:
            domain = expression.AND([domain, [('account_id', 'in', list(account_ids))]])
        domain = expression.AND([domain, exclude_ages_srb_wht_refund_domain()])
        return domain

    def _search_period_lines(self, account_ids=None):
        return self.env['account.move.line'].search(
            self._base_domain(date_scope='period', account_ids=account_ids),
            order='date, move_name, id',
        )

    def _prefetch_move_lines(self, move_lines):
        if not move_lines:
            return
        move_lines.mapped('move_id')
        move_lines.mapped('partner_id')
        move_lines.mapped('currency_id')
        move_lines.mapped('account_id')

    def _group_lines_by_account(self, move_lines):
        ids_by_account = defaultdict(list)
        for line in move_lines:
            if line.account_id:
                ids_by_account[line.account_id.id].append(line.id)
        Line = self.env['account.move.line']
        return {
            account_id: Line.browse(line_ids)
            for account_id, line_ids in ids_by_account.items()
        }

    def _sum_line_groups(self, lines_by_account):
        totals = {}
        for account_id, move_lines in lines_by_account.items():
            totals[account_id] = {
                'debit': sum(move_lines.mapped('debit')),
                'credit': sum(move_lines.mapped('credit')),
                'balance': sum(move_lines.mapped('balance')),
            }
        return totals

    def _read_group_by_account(self, date_scope, account_ids=None):
        groups = self.env['account.move.line'].read_group(
            self._base_domain(date_scope=date_scope, account_ids=account_ids),
            ['debit:sum', 'credit:sum', 'balance:sum'],
            ['account_id'],
            lazy=False,
        )
        totals = {}
        for group in groups:
            if not group.get('account_id'):
                continue
            totals[group['account_id'][0]] = {
                'debit': group.get('debit') or 0.0,
                'credit': group.get('credit') or 0.0,
                'balance': group.get('balance') or 0.0,
            }
        return totals

    def _initial_totals_by_account(self, account_ids=None):
        if not self.date_from:
            return {}
        grouped = self._read_group_by_account('before_period', account_ids)
        return {account_id: values['balance'] for account_id, values in grouped.items()}

    def _account_ids_from_totals(self, period_totals, initial_totals, allowed):
        rounding = self.currency.rounding
        account_ids = set(period_totals)
        for account_id, balance in initial_totals.items():
            if not float_is_zero(balance, precision_rounding=rounding):
                account_ids.add(account_id)
        if allowed is not None:
            account_ids = {account_id for account_id in account_ids if account_id in allowed}
        return sorted(account_ids)

    def _batch_extra_children(self, accounts, lines_by_account, include_details):
        if not include_details or 'opal.partner.ledger.hook' not in self.env:
            return {}
        hook = self.env['opal.partner.ledger.hook']
        partner_ids_by_account = {
            account.id: lines_by_account.get(account.id, self.env['account.move.line']).mapped('partner_id').ids
            for account in accounts
        }
        if hasattr(hook, 'get_accounts_children_map'):
            return hook.get_accounts_children_map(
                accounts, partner_ids_by_account, self.options, self.currency
            )
        return {
            account.id: hook.get_account_children(
                account, partner_ids_by_account.get(account.id), self.options, self.currency
            )
            for account in accounts
        }

    def _get_account_ids(self):
        period_totals = self._read_group_by_account('period')
        initial_totals = self._initial_totals_by_account()
        return self._account_ids_from_totals(period_totals, initial_totals, None)

    def _get_initial_balance(self, account):
        if not self.date_from:
            return 0.0
        domain = self._base_domain(date_scope='before_period') + [
            ('account_id', '=', account.id),
        ]
        groups = self.env['account.move.line'].read_group(
            domain, ['balance:sum'], [], lazy=False
        )
        return groups[0]['balance'] if groups else 0.0

    def _get_move_lines(self, account):
        domain = self._base_domain(date_scope='period') + [
            ('account_id', '=', account.id),
        ]
        return self.env['account.move.line'].search(
            domain,
            order='date, move_name, id',
        )

    def _communication(self, move_line):
        ref = move_line.ref or ''
        name = move_line.name or ''
        if ref and name and ref != name:
            return f"{ref} - {name}"
        return ref or name or move_line.move_name or ''

    def _build_account_line(
        self,
        account,
        include_details=False,
        move_lines=None,
        initial_balance=None,
        extra_children=None,
        period_debit=None,
        period_credit=None,
        period_balance=None,
    ):
        if initial_balance is None:
            initial_balance = self._get_initial_balance(account)
        if move_lines is None:
            move_lines = self._get_move_lines(account)
            if include_details:
                self._prefetch_move_lines(move_lines)
        if period_debit is None:
            period_debit = sum(move_lines.mapped('debit'))
        if period_credit is None:
            period_credit = sum(move_lines.mapped('credit'))
        if period_balance is None:
            period_balance = sum(move_lines.mapped('balance'))
        ending_balance = initial_balance + period_balance
        rounding = self.currency.rounding

        if (
            float_is_zero(period_debit, precision_rounding=rounding)
            and float_is_zero(period_credit, precision_rounding=rounding)
            and float_is_zero(initial_balance, precision_rounding=rounding)
        ):
            return None

        children = []
        if include_details:
            if self.date_from:
                children.append({
                    'id': f'account_{account.id}_initial',
                    'name': 'Initial Balance',
                    'level': 1,
                    'line_type': 'initial',
                    'foldable': False,
                    'account_id': account.id,
                    'date': False,
                    'communication': False,
                    'partner_name': False,
                    'amount_currency': False,
                    'currency_name': False,
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': initial_balance,
                    'children': [],
                })
            if extra_children is not None:
                children.extend(extra_children)
            else:
                children.extend(self._extra_children_after_initial(account, initial_balance, move_lines))

            running_balance = initial_balance
            for move_line in move_lines:
                running_balance += move_line.balance
                amount_currency = move_line.amount_currency
                currency_name = False
                if (
                    move_line.currency_id
                    and move_line.currency_id != self.currency
                ):
                    currency_name = move_line.currency_id.name
                children.append({
                    'id': f'aml_{move_line.id}',
                    'name': move_line.move_name or '',
                    'level': 1,
                    'line_type': 'move_line',
                    'foldable': False,
                    'account_id': account.id,
                    'move_line_id': move_line.id,
                    'move_id': move_line.move_id.id,
                    'date': fields.Date.to_string(move_line.date),
                    'communication': self._communication(move_line),
                    'partner_name': move_line.partner_id.display_name if move_line.partner_id else False,
                    'amount_currency': amount_currency if currency_name else False,
                    'currency_name': currency_name,
                    'debit': move_line.debit,
                    'credit': move_line.credit,
                    'balance': running_balance,
                    'children': [],
                })

        has_details = (
            not float_is_zero(period_debit, precision_rounding=rounding)
            or not float_is_zero(period_credit, precision_rounding=rounding)
            or (
                self.date_from
                and not float_is_zero(initial_balance, precision_rounding=rounding)
            )
        )

        return {
            'id': f'account_{account.id}',
            'name': account.display_name,
            'level': 0,
            'line_type': 'account',
            'foldable': has_details,
            'account_id': account.id,
            'account_code': account.code,
            'date': False,
            'communication': False,
            'partner_name': False,
            'amount_currency': False,
            'currency_name': False,
            'debit': period_debit,
            'credit': period_credit,
            'balance': ending_balance,
            'children': children,
        }

    def _extra_children_after_initial(self, account, initial_balance, move_lines):
        if 'opal.partner.ledger.hook' not in self.env:
            return []
        return self.env['opal.partner.ledger.hook'].get_account_children(
            account, move_lines.mapped('partner_id').ids, self.options, self.currency
        )

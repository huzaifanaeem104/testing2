# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import timedelta

from odoo import _, fields
from odoo.tools.float_utils import float_is_zero


REPORT_TYPES = {
    'receivable': {
        'account_type': 'asset_receivable',
        'title': 'Aged Receivable',
        'multiplicator': 1.0,
    },
    'payable': {
        'account_type': 'liability_payable',
        'title': 'Aged Payable',
        'multiplicator': -1.0,
    },
}

PERIOD_KEYS = tuple(f'period{index}' for index in range(6))


class AgedPartnerBalanceEngine:
    """Enterprise-compatible aged receivable/payable calculations.

    The open amount is reconstructed at ``date_to`` from the original journal
    item and only partial reconciliations whose ``max_date`` is on or before
    that date. This is deliberately not based on today's ``amount_residual``.
    """

    def __init__(self, env, options):
        self.env = env
        self.options = options or {}
        self.report_type = self.options.get('report_type') or 'receivable'
        if self.report_type not in REPORT_TYPES:
            self.report_type = 'receivable'
        self.config = REPORT_TYPES[self.report_type]
        self.date_to = fields.Date.to_date(
            self.options.get('date_to') or fields.Date.context_today(env.user)
        )
        self.aging_based_on = self.options.get('aging_based_on') or 'maturity'
        if self.aging_based_on not in ('maturity', 'invoice'):
            self.aging_based_on = 'maturity'
        self.aging_interval = max(int(self.options.get('aging_interval') or 30), 1)
        self.company = env.company
        self.currency = self.company.currency_id
        self.company_ids = tuple(env.companies.ids or [self.company.id])
        self.multiplicator = self.config['multiplicator']
        self._company_cache = {}
        self._currency_cache = {}
        self._partner_cache = {}
        self._account_cache = {}

    def get_report_data(self):
        partners = self._build_partner_lines_from_summary(
            self._fetch_summary_rows()
        )
        if self.options.get('unfold_all') and partners:
            details_by_partner = defaultdict(list)
            for row in self._fetch_rows():
                details_by_partner[row.get('partner_id') or False].append(
                    self._build_detail_line(row)
                )
            for partner_line in partners:
                partner_line['children'] = details_by_partner[
                    partner_line.get('partner_id') or False
                ]
        partners = self._sort_partner_lines(partners)
        total_line = self._build_total_line(partners)
        return {
            'title': self.config['title'],
            'report_type': self.report_type,
            'lines': [total_line] + partners,
            'columns': self._column_definitions(),
            'period_labels': self._period_labels(),
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol or self.currency.name,
            'currency_position': self.currency.position,
            'currency_label': _('In %s') % (
                '.%s' % (self.currency.symbol or self.currency.name)
            ),
            'date_label': fields.Date.to_string(self.date_to),
            'warnings': self._get_warnings(),
            'show_currency': bool(self.options.get('show_currency')),
            'show_account': bool(self.options.get('show_account')),
            'multi_currency': self.env.user.has_group('base.group_multi_currency'),
        }

    def get_partner_detail(self, partner_id):
        partner_id = int(partner_id) if partner_id else False
        rows = self._fetch_rows(
            partner_id=partner_id,
            unknown_partner_only=not partner_id,
        )
        return {
            'children': [
                self._build_detail_line(row)
                for row in sorted(
                    rows,
                    key=lambda item: (
                        item.get('invoice_date') or item['date'],
                        item['date'],
                        item['move_name'] or '',
                        item['id'],
                    ),
                )
            ],
        }

    def get_bucket_move_line_ids(self, partner_id, period_key='total'):
        partner_id = int(partner_id) if partner_id else False
        rows = self._fetch_rows(
            partner_id=partner_id,
            unknown_partner_only=not partner_id,
        )
        if period_key in PERIOD_KEYS:
            period_index = int(period_key[-1])
            rows = [
                row for row in rows
                if self._period_index(self._aging_date(row)) == period_index
            ]
        return [row['id'] for row in rows]

    def flatten_lines(self, lines=None, unfold_all=True):
        result = []
        for line in lines or []:
            result.append({key: value for key, value in line.items() if key != 'children'})
            if line.get('line_type') == 'partner' and unfold_all:
                result.extend(line.get('children') or [])
        return result

    def _query_filters(self, partner_id=None, unknown_partner_only=False):
        where = [
            'aml.company_id IN %s',
            'aml.date <= %s',
            'account.account_type = %s',
            "(aml.display_type IS NULL OR aml.display_type NOT IN ('line_section', 'line_note'))",
        ]
        params = [
            self.company_ids,
            self.date_to,
            self.config['account_type'],
        ]
        if self.options.get('all_entries'):
            where.append("move.state != 'cancel'")
        else:
            where.append("move.state = 'posted'")
        filter_trade = self.options.get('filter_trade', True)
        filter_non_trade = self.options.get('filter_non_trade', False)
        if filter_trade and not filter_non_trade:
            where.append('COALESCE(account.non_trade, FALSE) = FALSE')
        elif filter_non_trade and not filter_trade:
            where.append('COALESCE(account.non_trade, FALSE) = TRUE')

        selected_partner_ids = [
            int(selected_partner_id)
            for selected_partner_id in (self.options.get('partner_ids') or [])
            if selected_partner_id
        ]
        category_ids = [
            int(category_id)
            for category_id in (self.options.get('partner_category_ids') or [])
            if category_id
        ]
        if category_ids:
            tagged_ids = set(
                self.env['res.partner'].search([
                    ('category_id', 'in', category_ids),
                ]).ids
            )
            if selected_partner_ids:
                selected_partner_ids = [
                    partner_id for partner_id in selected_partner_ids
                    if partner_id in tagged_ids
                ]
            else:
                selected_partner_ids = list(tagged_ids)
            if not selected_partner_ids:
                where.append('FALSE')
        if selected_partner_ids:
            where.append('aml.partner_id IN %s')
            params.append(tuple(selected_partner_ids))
        if partner_id:
            where.append('aml.partner_id = %s')
            params.append(partner_id)
        elif unknown_partner_only:
            where.append('aml.partner_id IS NULL')
        return where, params

    def _period_table(self):
        periods = [(None, self.date_to, 0)]
        for index in range(1, 5):
            periods.append((
                self.date_to - timedelta(days=(self.aging_interval * (index - 1)) + 1),
                self.date_to - timedelta(days=self.aging_interval * index),
                index,
            ))
        periods.append((
            self.date_to - timedelta(days=(self.aging_interval * 4) + 1),
            None,
            5,
        ))
        values_sql = ', '.join(
            '(CAST(%s AS date), CAST(%s AS date), %s)'
            for _period in periods
        )
        params = [
            value
            for period in periods
            for value in period
        ]
        return values_sql, params

    def _fetch_summary_rows(self):
        if not self._trade_filter_domain_enabled():
            return []
        where, where_params = self._query_filters()
        period_sql, period_params = self._period_table()
        aging_field = (
            'aml.invoice_date'
            if self.aging_based_on == 'invoice'
            else 'aml.date_maturity'
        )
        precision = self.currency.decimal_places
        query = f"""
            WITH period_table(date_start, date_stop, period_index) AS (
                VALUES {period_sql}
            )
            SELECT
                aml.partner_id,
                aml.company_id,
                company.currency_id AS company_currency_id,
                period_table.period_index,
                MIN(COALESCE(aml.invoice_date, aml.date)) AS first_invoice_date,
                COUNT(aml.id) AS line_count,
                SUM(
                    aml.balance
                    - COALESCE(part_debit.amount, 0.0)
                    + COALESCE(part_credit.amount, 0.0)
                ) AS residual
            FROM account_move_line aml
            JOIN account_move move ON move.id = aml.move_id
            JOIN account_account account ON account.id = aml.account_id
            JOIN res_company company ON company.id = aml.company_id
            LEFT JOIN LATERAL (
                SELECT SUM(part.amount) AS amount
                FROM account_partial_reconcile part
                WHERE
                    part.max_date <= %s
                    AND part.debit_move_id = aml.id
            ) part_debit ON TRUE
            LEFT JOIN LATERAL (
                SELECT SUM(part.amount) AS amount
                FROM account_partial_reconcile part
                WHERE
                    part.max_date <= %s
                    AND part.credit_move_id = aml.id
            ) part_credit ON TRUE
            JOIN period_table ON
                (
                    period_table.date_start IS NULL
                    OR COALESCE({aging_field}, aml.date) <= period_table.date_start
                )
                AND
                (
                    period_table.date_stop IS NULL
                    OR COALESCE({aging_field}, aml.date) >= period_table.date_stop
                )
            WHERE {' AND '.join(where)}
            GROUP BY
                aml.partner_id,
                aml.company_id,
                company.currency_id,
                period_table.period_index
            HAVING
                ROUND(SUM(
                    CASE
                        WHEN aml.balance > 0
                        THEN aml.balance - COALESCE(part_debit.amount, 0.0)
                        ELSE 0.0
                    END
                )::numeric, %s) != 0
                OR ROUND(SUM(
                    CASE
                        WHEN aml.balance < 0
                        THEN -aml.balance - COALESCE(part_credit.amount, 0.0)
                        ELSE 0.0
                    END
                )::numeric, %s) != 0
            ORDER BY aml.partner_id NULLS LAST, period_table.period_index
        """
        self.env.cr.execute(
            query,
            [
                *period_params,
                self.date_to,
                self.date_to,
                *where_params,
                precision,
                precision,
            ],
        )
        rows = self.env.cr.dictfetchall()
        if rows:
            self._prefetch_summary_related(rows)
        return rows

    def _fetch_rows(self, partner_id=None, unknown_partner_only=False):
        if not self._trade_filter_domain_enabled():
            return []

        where, params = self._query_filters(
            partner_id=partner_id,
            unknown_partner_only=unknown_partner_only,
        )

        aging_field = (
            'aml.invoice_date'
            if self.aging_based_on == 'invoice'
            else 'aml.date_maturity'
        )
        query = f"""
            SELECT
                aml.id,
                aml.partner_id,
                aml.company_id,
                company.currency_id AS company_currency_id,
                aml.currency_id,
                aml.account_id,
                aml.journal_id,
                aml.move_id,
                aml.payment_id,
                aml.date,
                aml.invoice_date,
                aml.date_maturity,
                COALESCE({aging_field}, aml.date) AS aging_date,
                aml.name,
                aml.ref,
                move.name AS move_name,
                move.ref AS move_ref,
                (
                    aml.balance
                    - COALESCE(part_debit.amount, 0.0)
                    + COALESCE(part_credit.amount, 0.0)
                ) AS residual,
                (
                    aml.amount_currency
                    - COALESCE(part_debit.debit_amount_currency, 0.0)
                    + COALESCE(part_credit.credit_amount_currency, 0.0)
                ) AS residual_currency
            FROM account_move_line aml
            JOIN account_move move ON move.id = aml.move_id
            JOIN account_account account ON account.id = aml.account_id
            JOIN res_company company ON company.id = aml.company_id
            LEFT JOIN LATERAL (
                SELECT
                    SUM(part.amount) AS amount,
                    SUM(part.debit_amount_currency) AS debit_amount_currency
                FROM account_partial_reconcile part
                WHERE
                    part.max_date <= %s
                    AND part.debit_move_id = aml.id
            ) part_debit ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    SUM(part.amount) AS amount,
                    SUM(part.credit_amount_currency) AS credit_amount_currency
                FROM account_partial_reconcile part
                WHERE
                    part.max_date <= %s
                    AND part.credit_move_id = aml.id
            ) part_credit ON TRUE
            WHERE {' AND '.join(where)}
            ORDER BY aml.partner_id NULLS LAST, aml.date, aml.id
        """
        self.env.cr.execute(query, [self.date_to, self.date_to, *params])
        rows = self.env.cr.dictfetchall()
        if not rows:
            return []

        self._prefetch_related(rows)
        result = []
        for row in rows:
            company = self._company_cache[row['company_id']]
            company_currency = self._currency_cache[row['company_currency_id']]
            residual = row['residual'] or 0.0
            if float_is_zero(
                residual,
                precision_rounding=company_currency.rounding,
            ):
                continue
            conversion_rate = self._conversion_rate(company_currency, company)
            row['report_amount'] = self.currency.round(
                residual * conversion_rate * self.multiplicator
            )
            row['amount_currency'] = (
                (row['residual_currency'] or 0.0) * self.multiplicator
            )
            result.append(row)
        return result

    def _prefetch_summary_related(self, rows):
        company_ids = {row['company_id'] for row in rows}
        currency_ids = {row['company_currency_id'] for row in rows}
        partner_ids = {row['partner_id'] for row in rows if row.get('partner_id')}
        self._company_cache.update({
            company.id: company
            for company in self.env['res.company'].browse(company_ids)
        })
        self._currency_cache.update({
            currency.id: currency
            for currency in self.env['res.currency'].browse(currency_ids)
        })
        self._partner_cache.update({
            partner.id: partner
            for partner in self.env['res.partner'].browse(partner_ids)
        })

    def _prefetch_related(self, rows):
        company_ids = {row['company_id'] for row in rows}
        currency_ids = {
            currency_id
            for row in rows
            for currency_id in (
                row.get('company_currency_id'),
                row.get('currency_id'),
            )
            if currency_id
        }
        partner_ids = {row['partner_id'] for row in rows if row.get('partner_id')}
        account_ids = {row['account_id'] for row in rows if row.get('account_id')}

        self._company_cache.update({
            company.id: company
            for company in self.env['res.company'].browse(company_ids)
        })
        self._currency_cache.update({
            currency.id: currency
            for currency in self.env['res.currency'].browse(currency_ids)
        })
        self._partner_cache.update({
            partner.id: partner
            for partner in self.env['res.partner'].browse(partner_ids)
        })
        self._account_cache.update({
            account.id: account
            for account in self.env['account.account'].browse(account_ids)
        })

    def _conversion_rate(self, source_currency, company):
        if source_currency == self.currency:
            return 1.0
        return source_currency._convert(
            1.0,
            self.currency,
            company,
            self.date_to,
            round=False,
        )

    def _trade_filter_domain_enabled(self):
        return bool(
            self.options.get('filter_trade', True)
            or self.options.get('filter_non_trade', False)
        )

    def _build_partner_lines_from_summary(self, rows):
        rows_by_partner = defaultdict(list)
        for row in rows:
            rows_by_partner[row.get('partner_id') or False].append(row)

        partner_lines = []
        for partner_id, partner_rows in rows_by_partner.items():
            values = {key: 0.0 for key in PERIOD_KEYS}
            for row in partner_rows:
                company = self._company_cache[row['company_id']]
                company_currency = self._currency_cache[
                    row['company_currency_id']
                ]
                conversion_rate = self._conversion_rate(
                    company_currency,
                    company,
                )
                period_key = f"period{row['period_index']}"
                values[period_key] += (
                    (row['residual'] or 0.0)
                    * conversion_rate
                    * self.multiplicator
                )
            values = {
                key: self.currency.round(value)
                for key, value in values.items()
            }
            total = self.currency.round(sum(values.values()))
            if (
                self.options.get('hide_zero_lines')
                and float_is_zero(total, precision_rounding=self.currency.rounding)
            ):
                continue

            partner = self._partner_cache.get(partner_id)
            line = {
                'id': f"partner_{partner_id or 'none'}",
                'name': partner.display_name if partner else _('Unknown'),
                'level': 0,
                'line_type': 'partner',
                'foldable': any(row['line_count'] for row in partner_rows),
                'partner_id': partner_id,
                'invoice_date': False,
                'due_date': False,
                'amount_currency': False,
                'currency_id': False,
                'currency_name': False,
                'account_name': False,
                'total': total,
                'children': [],
                '_sort_invoice_date': min(
                    (
                        row['first_invoice_date']
                        for row in partner_rows
                        if row.get('first_invoice_date')
                    ),
                    default=self.date_to,
                ),
                **values,
            }
            if partner and 'trust' in partner._fields:
                line['trust'] = partner.with_company(
                    partner.company_id or self.company
                ).trust
            partner_lines.append(line)
        return partner_lines

    def _build_detail_line(self, row):
        period_index = self._period_index(self._aging_date(row))
        periods = {key: 0.0 for key in PERIOD_KEYS}
        periods[f'period{period_index}'] = row['report_amount']
        account = self._account_cache.get(row['account_id'])
        currency = self._currency_cache.get(row.get('currency_id'))
        communication = self._communication(row)
        return {
            'id': f"aml_{row['id']}",
            'name': row['move_name'] or communication or '/',
            'communication': communication,
            'level': 1,
            'line_type': 'move_line',
            'foldable': False,
            'partner_id': row.get('partner_id') or False,
            'move_line_id': row['id'],
            'move_id': row['move_id'],
            'invoice_date': (
                fields.Date.to_string(row['invoice_date'])
                if row.get('invoice_date')
                else False
            ),
            'due_date': (
                fields.Date.to_string(row['date_maturity'])
                if row.get('date_maturity')
                else fields.Date.to_string(row['date'])
            ),
            'date': fields.Date.to_string(row['date']),
            'amount_currency': row['amount_currency'],
            'currency_id': currency.id if currency else False,
            'currency_name': currency.name if currency else False,
            'account_name': (
                account.display_name if account else ''
            ),
            'account_code': account.code if account else '',
            'total': False,
            'children': [],
            **periods,
        }

    def _build_total_line(self, partner_lines):
        values = {
            key: self.currency.round(
                sum(line.get(key) or 0.0 for line in partner_lines)
            )
            for key in PERIOD_KEYS
        }
        return {
            'id': f'aged_{self.report_type}_total',
            'name': self.config['title'],
            'level': 0,
            'line_type': 'total',
            'foldable': False,
            'partner_id': False,
            'invoice_date': False,
            'due_date': False,
            'amount_currency': False,
            'currency_id': False,
            'currency_name': False,
            'account_name': False,
            'total': self.currency.round(sum(values.values())),
            'children': [],
            **values,
        }

    def _sort_partner_lines(self, lines):
        sort_by = self.options.get('sort_by') or 'name'
        direction = self.options.get('sort_direction') or 'asc'
        reverse = direction == 'desc'
        if sort_by == 'invoice_date':
            key = lambda line: (line.get('_sort_invoice_date') or self.date_to, line['name'])
        elif sort_by in (*PERIOD_KEYS, 'total'):
            key = lambda line: (line.get(sort_by) or 0.0, line['name'])
        else:
            key = lambda line: (line['name'] or '').lower()
        return sorted(lines, key=key, reverse=reverse)

    def _aging_date(self, row):
        return fields.Date.to_date(row['aging_date'])

    def _period_index(self, aging_date):
        days = (self.date_to - aging_date).days
        if days <= 0:
            return 0
        if days <= self.aging_interval:
            return 1
        if days <= self.aging_interval * 2:
            return 2
        if days <= self.aging_interval * 3:
            return 3
        if days <= self.aging_interval * 4:
            return 4
        return 5

    def _period_labels(self):
        interval = self.aging_interval
        return {
            'period0': _('At Date'),
            'period1': f'1-{interval}',
            'period2': f'{interval + 1}-{interval * 2}',
            'period3': f'{interval * 2 + 1}-{interval * 3}',
            'period4': f'{interval * 3 + 1}-{interval * 4}',
            'period5': _('Older'),
            'total': _('Total'),
        }

    def _column_definitions(self):
        labels = self._period_labels()
        columns = [
            {
                'key': 'invoice_date',
                'name': _('Invoice Date'),
                'type': 'date',
                'sortable': True,
            },
        ]
        if self.options.get('show_currency'):
            columns.extend([
                {
                    'key': 'amount_currency',
                    'name': _('Amount Currency'),
                    'type': 'amount_currency',
                    'sortable': False,
                },
                {
                    'key': 'currency_name',
                    'name': _('Currency'),
                    'type': 'string',
                    'sortable': False,
                },
            ])
        if self.options.get('show_account'):
            columns.append({
                'key': 'account_name',
                'name': _('Account'),
                'type': 'string',
                'sortable': False,
            })
        columns.extend([
            {
                'key': key,
                'name': labels[key],
                'type': 'monetary',
                'sortable': True,
                'auditable': True,
            }
            for key in (*PERIOD_KEYS, 'total')
        ])
        return columns

    def _communication(self, row):
        move_name = row.get('move_name') or ''
        for candidate in (row.get('name') or '', row.get('ref') or '', row.get('move_ref') or ''):
            if candidate and candidate != move_name:
                return candidate
        return ''

    def _get_warnings(self):
        draft_domain = [
            ('company_id', 'in', self.company_ids),
            ('parent_state', '=', 'draft'),
            ('date', '<=', self.date_to),
            ('account_id.account_type', '=', self.config['account_type']),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if self.env['account.move.line'].search_count(draft_domain, limit=1):
            return [_(
                'There are unposted Journal Entries prior or included in this period.'
            )]
        return []

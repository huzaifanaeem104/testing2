# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tools.float_utils import float_is_zero

from .balance_sheet_engine import BalanceSheetEngine
from .executive_summary_structure import EXECUTIVE_SUMMARY_SECTIONS
from .profit_loss_engine import ProfitLossEngine


class ExecutiveSummaryEngine:
    """Executive Summary KPI engine mirroring Odoo Enterprise."""

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
        self._values = {}

    def get_report_data(self):
        self._compute_values()
        lines = []
        for section in EXECUTIVE_SUMMARY_SECTIONS:
            children = []
            for child in section['children']:
                value = self._values.get(child['code'], 0.0)
                children.append({
                    'id': child['code'],
                    'name': child['name'],
                    'level': 1,
                    'balance': value,
                    'figure_type': child.get('figure_type', 'monetary'),
                    'foldable': False,
                    'line_type': 'metric',
                    'children': [],
                })
            lines.append({
                'id': section['code'],
                'name': section['name'],
                'level': 0,
                'balance': False,
                'figure_type': False,
                'foldable': True,
                'line_type': 'section',
                'children': children,
            })

        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'warnings': self._get_warnings(),
        }

    def flatten_lines(self, lines=None):
        result = []
        for section in lines or []:
            result.append({k: v for k, v in section.items() if k != 'children'})
            for child in section.get('children') or []:
                result.append(child)
        return result

    def _get_date_label(self):
        if self.date_from:
            if self.date_from.year == self.date_to.year and (
                self.date_from.month == 1
                and self.date_from.day == 1
                and self.date_to.month == 12
                and self.date_to.day == 31
            ):
                return str(self.date_from.year)
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

    def _base_domain(self, date_scope='period'):
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
        elif date_scope == 'to_date':
            domain.append(('date', '<=', self.date_to))
        return domain

    def _sum_field(self, extra_domain, date_scope='period', field='balance'):
        domain = self._base_domain(date_scope=date_scope) + list(extra_domain)
        groups = self.env['account.move.line'].read_group(
            domain, [f'{field}:sum'], [], lazy=False
        )
        return groups[0][field] if groups else 0.0

    def _pl_balance(self, code):
        engine = ProfitLossEngine(self.env, self.options)
        engine.get_report_data()
        return engine._balances.get(code, 0.0)

    def _bs_balance(self, code):
        engine = BalanceSheetEngine(self.env, self.options)
        engine.get_report_data()
        return engine._balances.get(code, 0.0)

    def _safe_div(self, numerator, denominator):
        if float_is_zero(denominator, precision_rounding=self.currency.rounding):
            return 0.0
        return numerator / denominator

    def _compute_values(self):
        cash_domain = [
            ('account_id.account_type', 'in', ('asset_cash', 'liability_credit_card')),
        ]
        cash_received = self._sum_field(
            cash_domain + [('debit', '>', 0.0)],
            date_scope='period',
            field='debit',
        )
        cash_spent = self._sum_field(
            cash_domain + [('credit', '>', 0.0)],
            date_scope='period',
            field='credit',
        )
        closing_bank = self._sum_field(cash_domain, date_scope='to_date')

        revenue = self._pl_balance('REV')
        cost_of_revenue = self._pl_balance('COS')
        gross_profit = self._pl_balance('GRP')
        expenses = self._pl_balance('EXP')
        net_profit = self._pl_balance('NEP')

        receivables = self._sum_field(
            [('account_id.account_type', '=', 'asset_receivable')],
            date_scope='to_date',
        )
        payables = self._sum_field(
            [('account_id.account_type', '=', 'liability_payable')],
            date_scope='to_date',
        )
        total_assets = self._bs_balance('TA')
        liabilities = self._bs_balance('L')
        current_assets = self._bs_balance('CA')
        current_liabilities = self._bs_balance('CL')

        n_days = (self.date_to - (self.date_from or self.date_to)).days or 1

        self._values = {
            'cash_received': cash_received,
            'cash_spent': -cash_spent,
            'cash_surplus': cash_received - cash_spent,
            'closing_bank_balance': closing_bank,
            'revenue': revenue,
            'cost_of_revenue': cost_of_revenue,
            'gross_profit': gross_profit,
            'expenses': expenses,
            'net_profit': net_profit,
            'receivables': receivables,
            'payables': payables,
            'net_assets': total_assets - liabilities,
            'gross_profit_margin': self._safe_div(gross_profit, revenue) * 100.0,
            'net_profit_margin': self._safe_div(net_profit, revenue) * 100.0,
            'return_on_investments': self._safe_div(net_profit, total_assets) * 100.0,
            'avg_debtors_days': self._safe_div(receivables, revenue) * n_days,
            'avg_creditors_days': self._safe_div(-payables, cost_of_revenue + expenses) * n_days,
            'short_term_cash_forecast': receivables + payables,
            'current_assets_to_liabilities': self._safe_div(current_assets, current_liabilities),
        }

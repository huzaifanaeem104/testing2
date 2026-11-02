# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tools.float_utils import float_is_zero

P_AND_L_ACCOUNT_TYPES = (
    'income',
    'income_other',
    'expense_direct_cost',
    'expense',
    'expense_depreciation',
)


class FinancialReportEngine:
    """Shared hierarchical financial report engine (Enterprise-style)."""

    report_structure = []
    date_label_fields = ('date_to',)

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
        self._balances = {}

    def get_report_data(self):
        lines = []
        for node in self.report_structure:
            built = self._build_node(node)
            if built:
                lines.append(built)
        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'warnings': self._get_warnings(),
        }

    def _get_date_label(self):
        if self.date_from and 'date_from' in self.date_label_fields:
            return f"{fields.Date.to_string(self.date_from)} — {fields.Date.to_string(self.date_to)}"
        return fields.Date.to_string(self.date_to)

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

    def _build_node(self, node):
        node_type = node.get('line_type', 'group')
        code = node['code']

        if node_type in ('expression', 'total') and node.get('expression'):
            balance = self._compute_expression(node['expression'])
            self._balances[code] = balance
            return self._line_dict(node, balance, children=[])

        if node.get('domain'):
            balance, accounts = self._sum_domain(
                node['domain'],
                sign=node.get('sign', 1),
                date_scope=node.get('date_scope', 'to_date'),
                groupby_account=node.get('foldable', False),
            )
            self._balances[code] = balance
            if node.get('hide_if_zero') and float_is_zero(balance, precision_digits=2):
                return None
            children = [
                self._account_line_dict(node, account, node.get('level', 0) + 1)
                for account in accounts
            ]
            return self._line_dict(node, balance, children=children)

        children_nodes = node.get('children') or []
        built_children = [self._build_node(child_node) for child_node in children_nodes]
        children = [child for child in built_children if child]
        if node.get('aggregation'):
            balance = sum(self._balances.get(code_key, 0.0) for code_key in node['aggregation'])
        else:
            balance = sum(child['balance'] for child in children)
        self._balances[code] = balance
        if node.get('hide_if_zero') and float_is_zero(balance, precision_digits=2):
            return None
        return self._line_dict(node, balance, children=children)

    def _line_dict(self, node, balance, children):
        return {
            'id': node['code'],
            'name': node['name'],
            'level': node.get('level', 0),
            'balance': balance,
            'foldable': bool(node.get('foldable') or children),
            'line_type': node.get('line_type', 'group'),
            'account_id': False,
            'children': children,
        }

    def _account_line_dict(self, parent_node, account, level):
        return {
            'id': f"{parent_node['code']}_{account['account_id']}",
            'name': account['name'],
            'level': level,
            'balance': account['balance'],
            'foldable': False,
            'line_type': 'account',
            'account_id': account['account_id'],
            'account_code': account['account_code'],
            'children': [],
        }

    def _compute_expression(self, expression):
        return 0.0

    def _base_domain(self, date_scope='to_date'):
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
        elif date_scope == 'to_date' or date_scope == 'from_beginning':
            domain.append(('date', '<=', self.date_to))
        elif date_scope == 'from_fiscalyear':
            fy_dates = self.company.compute_fiscalyear_dates(self.date_to)
            domain.extend([
                ('date', '>=', fy_dates['date_from']),
                ('date', '<=', self.date_to),
            ])

        journal_ids = self.options.get('journal_ids') or []
        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))

        analytic_id = self.options.get('analytic_account_id')
        if analytic_id:
            domain.append(('analytic_distribution', 'ilike', f'"{analytic_id}"'))
        return domain

    def _sum_domain(self, extra_domain, sign=1, date_scope='to_date', groupby_account=False):
        domain = self._base_domain(date_scope=date_scope) + list(extra_domain)
        aml = self.env['account.move.line']
        rounding = self.currency.rounding

        if groupby_account:
            groups = aml.read_group(domain, ['balance:sum'], ['account_id'], lazy=False)
            accounts = []
            total = 0.0
            for group in groups:
                if not group.get('account_id'):
                    continue
                account = self.env['account.account'].browse(group['account_id'][0])
                balance = (group['balance'] or 0.0) * sign
                if float_is_zero(balance, precision_rounding=rounding):
                    continue
                accounts.append({
                    'account_id': account.id,
                    'account_code': account.code,
                    'name': account.display_name,
                    'balance': balance,
                })
                total += balance
            accounts.sort(key=lambda row: row['account_code'] or '')
            return total, accounts

        groups = aml.read_group(domain, ['balance:sum'], [], lazy=False)
        balance = (groups[0]['balance'] or 0.0) * sign if groups else 0.0
        return balance, []

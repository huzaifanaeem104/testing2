# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tools.float_utils import float_is_zero


class TrialBalanceEngine:
    """Enterprise-style Trial Balance engine."""

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
        account_amounts = self._compute_account_amounts()
        if self.options.get('hierarchy', True):
            lines = self._build_hierarchy_lines(account_amounts)
        else:
            lines = self._build_flat_lines(account_amounts)

        totals = self._sum_lines(lines)
        lines.append({
            'id': 'total',
            'name': 'Total',
            'level': 0,
            'line_type': 'total',
            'foldable': False,
            'account_id': False,
            'initial_balance': totals['initial_balance'],
            'period_debit': totals['period_debit'],
            'period_credit': totals['period_credit'],
            'end_balance': totals['end_balance'],
            'children': [],
        })

        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'period_label': self._get_period_label(),
            'warnings': self._get_warnings(),
        }

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

    def _get_period_label(self):
        if self.date_from and self.date_to:
            month_end = self.date_from + relativedelta(months=1, days=-1)
            if self.date_from.day == 1 and self.date_to == month_end:
                return self.date_from.strftime('%b %Y')
        return self._get_date_label()

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
        elif date_scope == 'before_period':
            if self.date_from:
                domain.append(('date', '<', self.date_from))
            else:
                domain.append(('date', '<=', self.date_to))

        journal_ids = self.options.get('journal_ids') or []
        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))

        analytic_id = self.options.get('analytic_account_id')
        if analytic_id:
            domain.append(('analytic_distribution', 'ilike', f'"{analytic_id}"'))
        return domain

    def _read_group_by_account(self, domain):
        groups = self.env['account.move.line'].read_group(
            domain,
            ['debit:sum', 'credit:sum', 'balance:sum'],
            ['account_id'],
            lazy=False,
        )
        result = {}
        for group in groups:
            if not group.get('account_id'):
                continue
            account_id = group['account_id'][0]
            result[account_id] = {
                'debit': group['debit'] or 0.0,
                'credit': group['credit'] or 0.0,
                'balance': group['balance'] or 0.0,
            }
        return result

    def _compute_account_amounts(self):
        rounding = self.currency.rounding
        hide_zero = self.options.get('hide_zero_lines', False)

        period_data = self._read_group_by_account(self._base_domain('period'))
        before_data = {}
        if self.date_from:
            before_data = self._read_group_by_account(self._base_domain('before_period'))

        account_ids = set(period_data.keys()) | set(before_data.keys())
        accounts = self.env['account.account'].browse(sorted(account_ids))

        result = {}
        for account in accounts:
            before = before_data.get(account.id, {})
            period = period_data.get(account.id, {})
            initial_balance = before.get('balance', 0.0)
            period_debit = period.get('debit', 0.0)
            period_credit = period.get('credit', 0.0)
            end_balance = initial_balance + period.get('balance', 0.0)

            if hide_zero and all(
                float_is_zero(value, precision_rounding=rounding)
                for value in (initial_balance, period_debit, period_credit, end_balance)
            ):
                continue

            result[account.id] = {
                'initial_balance': initial_balance,
                'period_debit': period_debit,
                'period_credit': period_credit,
                'end_balance': end_balance,
                'account_code': account.code or '',
                'account_name': account.display_name,
            }
        return result

    def _amount_fields(self, amounts):
        return {
            'initial_balance': amounts['initial_balance'],
            'period_debit': amounts['period_debit'],
            'period_credit': amounts['period_credit'],
            'end_balance': amounts['end_balance'],
        }

    def _build_account_line(self, account_id, amounts, level=0):
        return {
            'id': f'account_{account_id}',
            'line_type': 'account',
            'name': amounts['account_name'],
            'account_id': account_id,
            'account_code': amounts['account_code'],
            'level': level,
            'foldable': False,
            **self._amount_fields(amounts),
            'children': [],
        }

    def _build_flat_lines(self, account_amounts):
        lines = []
        sorted_items = sorted(
            account_amounts.items(),
            key=lambda item: item[1]['account_code'],
        )
        for account_id, amounts in sorted_items:
            lines.append(self._build_account_line(account_id, amounts, level=0))
        return lines

    def _sum_lines(self, lines):
        totals = {
            'initial_balance': 0.0,
            'period_debit': 0.0,
            'period_credit': 0.0,
            'end_balance': 0.0,
        }
        for line in lines:
            if line.get('line_type') == 'subtotal':
                continue
            for key in totals:
                totals[key] += line.get(key, 0.0)
        for key in totals:
            totals[key] = self.currency.round(totals[key])
        return totals

    def _make_subtotal_line(self, name, amounts, level, line_id):
        return {
            'id': line_id,
            'line_type': 'subtotal',
            'name': name,
            'account_id': False,
            'level': level,
            'foldable': False,
            **amounts,
            'children': [],
        }

    def _build_hierarchy_lines(self, account_amounts):
        if not account_amounts:
            return []

        Group = self.env['account.group']
        accounts = self.env['account.account'].browse(list(account_amounts.keys()))

        by_group = {}
        ungrouped = []
        for account in accounts:
            line = self._build_account_line(account.id, account_amounts[account.id])
            if account.group_id:
                by_group.setdefault(account.group_id.id, []).append(line)
            else:
                ungrouped.append(line)

        if not by_group:
            return self._build_flat_lines(account_amounts)

        group_ids = set(by_group.keys())
        groups = Group.browse(list(group_ids))
        all_groups = groups
        pending_parents = groups.parent_id
        while pending_parents:
            all_groups |= pending_parents
            pending_parents = pending_parents.parent_id

        group_records = all_groups.sorted(
            key=lambda group: (group.code_prefix_start or '', group.id)
        )
        children_groups = {}
        for group in group_records:
            if group.parent_id and group.parent_id.id in all_groups.ids:
                children_groups.setdefault(group.parent_id.id, []).append(group)

        def build_group_node(group, level):
            child_group_records = children_groups.get(group.id, [])
            child_group_records = sorted(
                child_group_records,
                key=lambda g: (g.code_prefix_start or '', g.id),
            )

            children = []
            for child_group in child_group_records:
                child_node = build_group_node(child_group, level + 1)
                if child_node:
                    children.append(child_node)

            account_children = sorted(
                by_group.get(group.id, []),
                key=lambda line: line.get('account_code') or '',
            )
            for account_line in account_children:
                account_line['level'] = level + 1
                children.append(account_line)

            if not children:
                return None

            amounts = self._sum_lines(children)
            subtotal = self._make_subtotal_line(
                f'Total {group.display_name}',
                amounts,
                level + 1,
                f'group_{group.id}_total',
            )
            node_children = list(children) + [subtotal]

            return {
                'id': f'group_{group.id}',
                'line_type': 'group',
                'name': group.display_name,
                'group_id': group.id,
                'account_id': False,
                'level': level,
                'foldable': True,
                **amounts,
                'children': node_children,
            }

        roots = [
            group for group in group_records
            if not group.parent_id or group.parent_id.id not in all_groups.ids
        ]
        roots = sorted(roots, key=lambda g: (g.code_prefix_start or '', g.id))

        lines = []
        for root in roots:
            node = build_group_node(root, 0)
            if node:
                lines.append(node)

        if ungrouped:
            ungrouped = sorted(ungrouped, key=lambda line: line.get('account_code') or '')
            for line in ungrouped:
                line['level'] = 1
            amounts = self._sum_lines(ungrouped)
            lines.append({
                'id': 'group_uncategorized',
                'line_type': 'group',
                'name': 'Uncategorized',
                'group_id': False,
                'account_id': False,
                'level': 0,
                'foldable': True,
                **amounts,
                'children': ungrouped + [
                    self._make_subtotal_line(
                        'Total Uncategorized',
                        amounts,
                        1,
                        'group_uncategorized_total',
                    ),
                ],
            })

        return lines

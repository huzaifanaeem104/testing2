# -*- coding: utf-8 -*-

from odoo import fields

from .report_display import clip_project_name
from .project_directory_ledger_common import (
    apply_account_payable_visibility,
    apply_bank_visibility,
    apply_cost_of_revenue_visibility,
    apply_target_move_domain,
    build_filter_labels,
    compute_grand_totals,
    compute_group_running_balances,
    get_group_by_label,
    resolve_line_project,
)


class ProjectDirectoryLedgerEngine:
    """Build grouped Project Directory Ledger data for PDF and interactive UI."""

    def __init__(self, env, form):
        self.env = env
        self.form = form or {}
        self.company = env.company
        self.currency = self.company.currency_id
        self._project_cache = {}

    def get_report_data(self):
        grouped_data, group_by, line_project_names = self._build_grouped_data()
        running_balances = compute_group_running_balances(grouped_data)
        lines = self._build_lines(grouped_data, group_by, running_balances, line_project_names)
        date_label = self._date_label()
        return {
            'lines': lines,
            'group_by': group_by,
            'group_by_label': get_group_by_label(group_by),
            'show_analytic_col': group_by != 'analytic_distribution',
            'currency_id': self.currency.id,
            'date_label': date_label,
            'filter_labels': build_filter_labels(self.env, self.form),
            'grand_totals': compute_grand_totals(grouped_data),
            'group_count': len(grouped_data),
            'line_count': sum(len(group_lines) for group_lines in grouped_data.values()),
            'grouped_data': grouped_data,
            'line_project_names': line_project_names,
            'running_balances': running_balances,
        }

    def _date_label(self):
        date_from = self.form.get('date_from')
        date_to = self.form.get('date_to')
        if date_from and date_to:
            return (
                f"{fields.Date.to_string(date_from)} — "
                f"{fields.Date.to_string(date_to)}"
            )
        if date_to:
            return fields.Date.to_string(date_to)
        if date_from:
            return fields.Date.to_string(date_from)
        return fields.Date.to_string(fields.Date.context_today(self.env.user))

    def _build_grouped_data(self):
        domain = [('display_type', 'not in', ('line_section', 'line_note'))]
        if self.form.get('date_from'):
            domain.append(('date', '>=', self.form['date_from']))
        if self.form.get('date_to'):
            domain.append(('date', '<=', self.form['date_to']))
        if self.form.get('account_id'):
            domain.append(('account_id', '=', self.form['account_id']))
        if self.form.get('partner_id'):
            domain.append(('partner_id', '=', self.form['partner_id']))
        apply_target_move_domain(domain, self.form)

        move_lines = self.env['account.move.line'].search(domain, order='date asc, id asc')
        target_aa_id = self.form.get('analytic_account_id')
        target_sub_company_id = self.form.get('sub_company_id')

        if target_sub_company_id:
            move_lines = move_lines.filtered(
                lambda line: self._line_matches_sub_company(line, target_sub_company_id)
            )

        if target_aa_id:
            move_lines = move_lines.filtered(
                lambda line: self._get_line_project(line).id == target_aa_id
            )

        move_lines = apply_account_payable_visibility(move_lines, self.form)
        move_lines = apply_cost_of_revenue_visibility(move_lines, self.form)
        move_lines = apply_bank_visibility(move_lines, self.form)

        partner_id = self.form.get('partner_id')
        if partner_id and not target_aa_id:
            group_by = 'partner_id'
        elif target_aa_id and not partner_id:
            group_by = 'analytic_distribution'
        else:
            group_by = 'analytic_distribution'

        grouped_data = {}
        line_project_names = {}
        for line in move_lines:
            if group_by == 'analytic_distribution':
                aa = self._get_line_project(line)
                key_name = clip_project_name(aa.name) if aa else 'Uncategorized'
                line_project_names[line.id] = clip_project_name(aa.name) if aa else ''
            else:
                key_name = line.partner_id.name if line.partner_id else 'No Partner'
                aa = self._get_line_project(line)
                line_project_names[line.id] = clip_project_name(aa.name) if aa else ''

            grouped_data.setdefault(key_name, []).append(line)

        return grouped_data, group_by, line_project_names

    def _line_matches_sub_company(self, line, sub_company_id):
        """Match Active Company via move header or analytic → contract chain."""
        move = line.move_id
        if move.ages_sub_company_id and move.ages_sub_company_id.id == sub_company_id:
            return True
        aa = self._get_line_project(line)
        if aa and aa.ages_contract_id and aa.ages_contract_id.sub_company_id.id == sub_company_id:
            return True
        if move.ages_project_id and move.ages_project_id.ages_contract_id:
            return move.ages_project_id.ages_contract_id.sub_company_id.id == sub_company_id
        return False

    def _get_line_project(self, line):
        return resolve_line_project(line, self._project_cache)

    def _build_lines(self, grouped_data, group_by, running_balances, line_project_names):
        lines = []
        total_debit = total_credit = 0.0

        for group_key in sorted(grouped_data.keys()):
            group_lines = grouped_data[group_key]
            group_debit = sum(line.debit for line in group_lines)
            group_credit = sum(line.credit for line in group_lines)
            group_balance = sum(line.balance for line in group_lines)
            total_debit += group_debit
            total_credit += group_credit

            first_line = group_lines[0]
            aa = self._get_line_project(first_line)
            partner = first_line.partner_id

            children = [
                self._move_line_dict(line, running_balances, line_project_names)
                for line in group_lines
            ]

            slug = group_key.lower().replace(' ', '_').replace('/', '_')[:40]
            lines.append({
                'id': f'group_{slug}_{first_line.id}',
                'name': group_key,
                'line_type': 'group',
                'foldable': bool(children),
                'level': 0,
                'group_by': group_by,
                'group_key': group_key,
                'partner_id': partner.id if group_by == 'partner_id' and partner else False,
                'analytic_account_id': aa.id if group_by == 'analytic_distribution' and aa else False,
                'debit': group_debit,
                'credit': group_credit,
                'balance': group_balance,
                'line_count': len(group_lines),
                'children': children,
            })

        lines.append({
            'id': 'total',
            'name': 'Total',
            'line_type': 'total',
            'foldable': False,
            'level': 0,
            'debit': total_debit,
            'credit': total_credit,
            'balance': self.currency.round(total_debit - total_credit),
            'children': [],
        })
        return lines

    def _move_line_dict(self, line, running_balances, line_project_names):
        amount_currency = line.amount_currency
        currency_name = False
        if line.currency_id and line.currency_id != self.currency:
            currency_name = line.currency_id.name

        account = line.account_id
        return {
            'id': f'aml_{line.id}',
            'line_type': 'move_line',
            'level': 1,
            'foldable': False,
            'move_line_id': line.id,
            'move_id': line.move_id.id,
            'name': line.move_id.name or '',
            'date': fields.Date.to_string(line.date) if line.date else False,
            'communication': line.name or '',
            'partner_id': line.partner_id.id if line.partner_id else False,
            'partner_name': line.partner_id.display_name if line.partner_id else '',
            'account_id': account.id if account else False,
            'account_code': account.code if account else '',
            'account_name': account.display_name if account else '',
            'analytic_name': line_project_names.get(line.id, ''),
            'amount_currency': amount_currency if currency_name else False,
            'currency_name': currency_name,
            'debit': line.debit,
            'credit': line.credit,
            'balance': running_balances.get(line.id, line.balance),
            'children': [],
        }

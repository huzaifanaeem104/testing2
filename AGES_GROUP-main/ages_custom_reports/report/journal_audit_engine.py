# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields
from odoo.tools.float_utils import float_is_zero


class JournalAuditEngine:
    """Enterprise-style Journal Audit engine."""

    date_label_fields = ('date_from', 'date_to')

    JOURNAL_TYPE_ORDER = {
        'sale': 1,
        'purchase': 2,
        'general': 3,
        'bank': 4,
        'cash': 5,
    }

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
        journal_lines = self._build_journal_lines()
        return {
            'lines': journal_lines,
            'tax_summary': self._get_global_tax_summary(),
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'warnings': self._get_warnings(),
        }

    def get_journal_accounts(self, journal_id):
        journal = self.env['account.journal'].browse(journal_id)
        line = self._build_journal_line(journal, include_accounts=True)
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
            if unfold_all or node.get('id') in unfolded_ids or not node.get('foldable'):
                for child in children:
                    _walk(child)

        for line in lines or []:
            _walk(line)
        return result

    def _get_date_label(self):
        if self.date_from:
            if (
                self.date_from.year == self.date_to.year
                and self.date_from.month == 1
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

    def _base_domain(self):
        domain = [
            ('company_id', 'child_of', self.company.id),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if self.options.get('target_move') == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        domain.append(('date', '<=', self.date_to))

        journal_ids = self.options.get('journal_ids') or []
        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))
        return domain

    def _get_journals(self):
        domain = self._base_domain()
        groups = self.env['account.move.line'].read_group(
            domain, ['debit:sum', 'credit:sum'], ['journal_id'], lazy=False
        )
        journal_ids = [
            group['journal_id'][0]
            for group in groups
            if group.get('journal_id')
        ]
        journals = self.env['account.journal'].browse(journal_ids)
        return journals.sorted(
            key=lambda journal: (
                self.JOURNAL_TYPE_ORDER.get(journal.type, 99),
                journal.sequence,
                journal.code or '',
            )
        )

    def _build_journal_lines(self):
        lines = []
        for journal in self._get_journals():
            journal_line = self._build_journal_line(
                journal, include_accounts=self.options.get('unfold_all', False)
            )
            if journal_line:
                lines.append(journal_line)
        return lines

    def _build_journal_line(self, journal, include_accounts=False):
        domain = self._base_domain() + [('journal_id', '=', journal.id)]
        aml = self.env['account.move.line']

        journal_groups = aml.read_group(
            domain, ['debit:sum', 'credit:sum'], [], lazy=False
        )
        if not journal_groups:
            return None

        period_debit = journal_groups[0]['debit'] or 0.0
        period_credit = journal_groups[0]['credit'] or 0.0
        rounding = self.currency.rounding

        if (
            float_is_zero(period_debit, precision_rounding=rounding)
            and float_is_zero(period_credit, precision_rounding=rounding)
        ):
            return None

        account_groups = aml.read_group(
            domain,
            ['debit:sum', 'credit:sum', 'balance:sum'],
            ['account_id'],
            lazy=False,
        )

        children = []
        if include_accounts:
            accounts = self.env['account.account'].browse([
                group['account_id'][0]
                for group in account_groups
                if group.get('account_id')
            ]).sorted(key=lambda acc: acc.code or '')

            account_map = {
                group['account_id'][0]: group
                for group in account_groups
                if group.get('account_id')
            }

            for account in accounts:
                group = account_map.get(account.id, {})
                debit = group.get('debit') or 0.0
                credit = group.get('credit') or 0.0
                balance = group.get('balance') or 0.0
                if (
                    float_is_zero(debit, precision_rounding=rounding)
                    and float_is_zero(credit, precision_rounding=rounding)
                ):
                    continue
                children.append({
                    'id': f'journal_{journal.id}_account_{account.id}',
                    'name': account.display_name,
                    'code': account.code or '',
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'level': 1,
                    'line_type': 'account',
                    'foldable': False,
                    'journal_id': journal.id,
                    'account_id': account.id,
                    'children': [],
                })

        return {
            'id': f'journal_{journal.id}',
            'name': journal.name,
            'code': journal.code or '',
            'debit': period_debit,
            'credit': period_credit,
            'balance': False,
            'level': 0,
            'line_type': 'journal',
            'foldable': bool(account_groups),
            'journal_id': journal.id,
            'account_id': False,
            'children': children,
        }

    def _get_global_tax_summary(self):
        domain = self._base_domain()
        aml = self.env['account.move.line']
        rounding = self.currency.rounding

        taxes_applied = []
        tax_lines = aml.search(domain + [('tax_line_id', '!=', False)])
        tax_values = defaultdict(lambda: {
            'base_amount': 0.0,
            'tax_amount': 0.0,
        })

        for line in tax_lines:
            tax = line.tax_line_id
            tax_values[tax.id]['name'] = tax.display_name
            tax_values[tax.id]['tax_id'] = tax.id
            tax_values[tax.id]['tax_amount'] += abs(line.balance)
            tax_values[tax.id]['base_amount'] += abs(line.tax_base_amount or 0.0)

        for values in sorted(tax_values.values(), key=lambda row: row.get('name', '')):
            if float_is_zero(values['tax_amount'], precision_rounding=rounding):
                continue
            taxes_applied.append({
                'id': f"tax_{values['tax_id']}",
                'name': values['name'],
                'base_amount': values['base_amount'],
                'tax_amount': values['tax_amount'],
                'non_deductible': values['tax_amount'],
                'tax_id': values['tax_id'],
            })

        tax_grids = []
        grid_lines = aml.search(domain + [('tax_tag_ids', '!=', False)])
        grid_map = defaultdict(lambda: {'plus': 0.0, 'minus': 0.0, 'tag_ids': set()})

        for line in grid_lines:
            sign = -1 if line.tax_tag_invert else 1
            for tag in line.tax_tag_ids.filtered(lambda t: t.applicability == 'taxes'):
                name = tag.name or ''
                if name.startswith('+') or name.startswith('-'):
                    name = name[1:].strip()
                balance = line.balance * sign
                if tag.tax_negate:
                    balance = -balance
                bucket = grid_map[name]
                bucket['tag_ids'].add(tag.id)
                if balance >= 0:
                    bucket['plus'] += balance
                else:
                    bucket['minus'] += abs(balance)

        for name, values in sorted(grid_map.items()):
            impact = values['plus'] - values['minus']
            if (
                float_is_zero(values['plus'], precision_rounding=rounding)
                and float_is_zero(values['minus'], precision_rounding=rounding)
            ):
                continue
            tag_ids = sorted(values['tag_ids'])
            tax_grids.append({
                'id': f"grid_{tag_ids[0]}",
                'name': name,
                'plus': values['plus'],
                'minus': values['minus'],
                'impact': impact,
                'tag_ids': tag_ids,
            })

        if not taxes_applied and not tax_grids:
            return False

        return {
            'taxes_applied': taxes_applied,
            'tax_grids': tax_grids,
            'show_non_deductible': bool(taxes_applied),
        }

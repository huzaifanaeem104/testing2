# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields
from odoo.osv import expression
from odoo.tools.float_utils import float_is_zero

from .project_directory_ledger_common import primary_analytic_id_from_distribution
from .report_display import clip_project_name
from .report_filter_domains import (
    analytic_reach_domain,
    exclude_ages_srb_wht_refund_domain,
    journal_reach_domain,
    partner_reach_domain,
)


ACCOUNT_FILTER_DOMAINS = {
    'receivable': [
        ('account_id.account_type', '=', 'asset_receivable'),
        ('account_id.non_trade', '=', False),
    ],
    'non_trade_receivable': [
        ('account_id.account_type', '=', 'asset_receivable'),
        ('account_id.non_trade', '=', True),
    ],
    'payable': [
        ('account_id.account_type', '=', 'liability_payable'),
        ('account_id.non_trade', '=', False),
    ],
    'non_trade_payable': [
        ('account_id.account_type', '=', 'liability_payable'),
        ('account_id.non_trade', '=', True),
    ],
}


class PartnerLedgerEngine:
    """Enterprise-style Partner Ledger engine."""

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
        self._project_name_cache = {}

    def get_report_data(self):
        include_details = self.options.get('unfold_all', False)
        selected_ids = self._selected_partner_ids()
        period_lines = None
        lines_by_partner = {}

        if include_details or selected_ids:
            period_lines = self._search_period_lines()
            self._prefetch_move_lines(period_lines)
            lines_by_partner = self._group_lines_by_partner(period_lines, selected_ids)
            period_totals = self._sum_line_groups(lines_by_partner)
        else:
            period_totals = self._read_group_by_partner('period')

        initial_totals = self._initial_totals_by_partner(selected_ids)
        partner_ids = self._partner_ids_from_totals(
            period_totals, initial_totals, selected_ids
        )
        partners = self._browse_partners(partner_ids)
        need_extra = include_details or bool(self.options.get('show_opal_balance'))
        extra_by_partner = self._batch_extra_children(partners, need_extra)

        lines = []
        total_debit = total_credit = 0.0
        empty = self.env['account.move.line']
        for partner in partners:
            partner_id = partner.id if partner else False
            period = period_totals.get(partner_id) or {
                'debit': 0.0, 'credit': 0.0, 'balance': 0.0,
            }
            extra_children = extra_by_partner.get(partner_id, []) if need_extra else None
            partner_line = self._build_partner_line(
                partner,
                include_details=include_details,
                move_lines=lines_by_partner.get(partner_id, empty) if include_details else empty,
                initial_balance=initial_totals.get(partner_id, 0.0),
                extra_children=extra_children,
                period_debit=period['debit'],
                period_credit=period['credit'],
                period_balance=period['balance'],
            )
            if partner_line:
                lines.append(partner_line)
                total_debit += partner_line['debit']
                total_credit += partner_line['credit']

        lines.append({
            'id': 'total',
            'name': 'Total',
            'level': 0,
            'line_type': 'total',
            'foldable': False,
            'partner_id': False,
            'journal_code': False,
            'account_code': False,
            'analytic_name': '',
            'date': False,
            'due_date': False,
            'matching_number': False,
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

    def get_partner_detail(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id) if partner_id else False
        line = self._build_partner_line(partner, include_details=True)
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

    def _account_type_domain(self):
        if self.options.get('account_ids'):
            return []
        if 'account_filters' in self.options:
            filters = self.options.get('account_filters') or []
        else:
            filters = ['receivable', 'payable']
        domains = [
            ACCOUNT_FILTER_DOMAINS[key]
            for key in filters
            if key in ACCOUNT_FILTER_DOMAINS
        ]
        if not domains:
            return []
        if len(domains) == 1:
            return list(domains[0])
        return expression.OR(domains)

    def _base_domain(self, date_scope='period'):
        domain = [
            ('company_id', 'child_of', self.company.id),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        type_domain = self._account_type_domain()
        if type_domain:
            domain = domain + type_domain

        if self.options.get('target_move') == 'posted':
            domain.append(('parent_state', '=', 'posted'))

        partner_domain = partner_reach_domain(self.env, self.options.get('partner_ids'))
        if partner_domain:
            domain = expression.AND([domain, partner_domain])

        account_ids = self.options.get('account_ids') or []
        if account_ids:
            domain.append(('account_id', 'in', account_ids))

        journal_domain = journal_reach_domain(self.env, self.options.get('journal_ids'))
        if journal_domain:
            domain = expression.AND([domain, journal_domain])

        analytic_domain = self._analytic_domain()
        if analytic_domain:
            domain = expression.AND([domain, analytic_domain])

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

        domain = expression.AND([domain, exclude_ages_srb_wht_refund_domain()])
        return domain

    def _analytic_domain(self):
        """Limit to one project / analytic, including bills whose payable line has none."""
        analytic_id = self.options.get('analytic_account_id')
        if not analytic_id:
            return []
        domains = [analytic_reach_domain(self.env, [analytic_id])]
        token = f'"{int(analytic_id)}"'
        domains.append([
            ('move_id.move_type', 'in', (
                'in_invoice', 'in_refund', 'out_invoice', 'out_refund',
                'in_receipt', 'out_receipt',
            )),
            ('move_id.line_ids.analytic_distribution', 'ilike', token),
        ])
        return expression.OR([domain for domain in domains if domain])

    def _line_project_name(self, line):
        aa_id = primary_analytic_id_from_distribution(line.analytic_distribution)
        move = line.move_id
        if not aa_id and 'ages_analytic_account_id' in move._fields and move.ages_analytic_account_id:
            aa_id = move.ages_analytic_account_id.id
        if (
            not aa_id
            and 'ages_project_id' in move._fields
            and move.ages_project_id
            and move.ages_project_id.account_id
        ):
            aa_id = move.ages_project_id.account_id.id
        if not aa_id and move.is_invoice(include_receipts=True):
            for sibling in move.line_ids:
                aa_id = primary_analytic_id_from_distribution(sibling.analytic_distribution)
                if aa_id:
                    break
        if not aa_id:
            return ''
        if aa_id not in self._project_name_cache:
            analytic = self.env['account.analytic.account'].browse(aa_id)
            self._project_name_cache[aa_id] = clip_project_name(
                analytic.name or analytic.display_name or ''
            )
        return self._project_name_cache[aa_id]

    def _selected_partner_ids(self):
        return [
            int(partner_id)
            for partner_id in (self.options.get('partner_ids') or [])
            if partner_id
        ]

    def _search_period_lines(self):
        return self.env['account.move.line'].search(
            self._base_domain(date_scope='period'),
            order='date, move_name, id',
        )

    def _prefetch_inference(self, move_lines):
        if not move_lines:
            return
        moves = move_lines.mapped('move_id')
        if 'ages_project_id' in moves._fields:
            moves.mapped('ages_project_id.partner_id')
        if 'ages_analytic_account_id' in moves._fields:
            moves.mapped('ages_analytic_account_id.partner_id')

    def _prefetch_move_lines(self, move_lines):
        if not move_lines:
            return
        move_lines.mapped('journal_id')
        move_lines.mapped('account_id')
        move_lines.mapped('partner_id')
        move_lines.mapped('currency_id')
        moves = move_lines.mapped('move_id')
        self._prefetch_inference(move_lines)
        if 'ages_analytic_account_id' in moves._fields:
            moves.mapped('ages_analytic_account_id')
        if 'ages_project_id' in moves._fields:
            moves.mapped('ages_project_id.account_id')
        if 'origin_payment_id' in moves._fields:
            payments = moves.mapped('origin_payment_id')
            if payments and 'withholding_line_ids' in payments._fields:
                payments.mapped('withholding_line_ids.amount')
        moves.mapped('line_ids.analytic_distribution')
        self._warm_project_name_cache(move_lines, moves)

    def _warm_project_name_cache(self, move_lines, moves):
        aa_ids = set()
        for line in move_lines:
            aa_id = primary_analytic_id_from_distribution(line.analytic_distribution)
            if aa_id:
                aa_ids.add(aa_id)
        if 'ages_analytic_account_id' in moves._fields:
            aa_ids.update(moves.mapped('ages_analytic_account_id').ids)
        if 'ages_project_id' in moves._fields:
            aa_ids.update(moves.mapped('ages_project_id.account_id').ids)
        for move in moves:
            if not move.is_invoice(include_receipts=True):
                continue
            for sibling in move.line_ids:
                aa_id = primary_analytic_id_from_distribution(sibling.analytic_distribution)
                if aa_id:
                    aa_ids.add(aa_id)
        missing = [aa_id for aa_id in aa_ids if aa_id and aa_id not in self._project_name_cache]
        if not missing:
            return
        for analytic in self.env['account.analytic.account'].browse(missing):
            self._project_name_cache[analytic.id] = clip_project_name(
                analytic.name or analytic.display_name or ''
            )

    def _assign_partner_id(self, line, selected_ids=None):
        if selected_ids and len(selected_ids) == 1:
            return selected_ids[0]
        inferred = self._inferred_partner_id(line)
        if not selected_ids:
            return inferred
        if inferred in selected_ids:
            return inferred
        if line.partner_id and line.partner_id.id in selected_ids:
            return line.partner_id.id
        return inferred

    def _group_lines_by_partner(self, move_lines, selected_ids=None):
        ids_by_partner = defaultdict(list)
        for line in move_lines:
            ids_by_partner[self._assign_partner_id(line, selected_ids)].append(line.id)
        Line = self.env['account.move.line']
        return {
            partner_id: Line.browse(line_ids)
            for partner_id, line_ids in ids_by_partner.items()
        }

    def _sum_line_groups(self, lines_by_partner):
        totals = {}
        for partner_id, move_lines in lines_by_partner.items():
            totals[partner_id] = {
                'debit': sum(move_lines.mapped('debit')),
                'credit': sum(move_lines.mapped('credit')),
                'balance': sum(move_lines.mapped('balance')),
            }
        return totals

    def _empty_amount(self):
        return {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}

    def _read_group_by_partner(self, date_scope):
        groups = self.env['account.move.line'].read_group(
            self._base_domain(date_scope=date_scope),
            ['debit:sum', 'credit:sum', 'balance:sum'],
            ['partner_id'],
            lazy=False,
        )
        totals = {}
        has_orphan = False
        for group in groups:
            partner_id = group['partner_id'][0] if group.get('partner_id') else False
            totals[partner_id] = {
                'debit': group.get('debit') or 0.0,
                'credit': group.get('credit') or 0.0,
                'balance': group.get('balance') or 0.0,
            }
            if partner_id is False:
                has_orphan = True
        if has_orphan:
            self._rebucket_orphans(totals, date_scope)
        return totals

    def _rebucket_orphans(self, totals, date_scope):
        orphans = self.env['account.move.line'].search(expression.AND([
            self._base_domain(date_scope=date_scope),
            [('partner_id', '=', False)],
        ]))
        totals.pop(False, None)
        if not orphans:
            return
        self._prefetch_inference(orphans)
        for line in orphans:
            partner_id = self._inferred_partner_id(line)
            dest = totals.setdefault(partner_id, self._empty_amount())
            dest['debit'] += line.debit
            dest['credit'] += line.credit
            dest['balance'] += line.balance

    def _initial_totals_by_partner(self, selected_ids=None):
        if not self.date_from:
            return {}
        if selected_ids:
            lines = self.env['account.move.line'].search(
                self._base_domain(date_scope='before_period')
            )
            self._prefetch_inference(lines)
            totals = defaultdict(float)
            for line in lines:
                totals[self._assign_partner_id(line, selected_ids)] += line.balance
            return dict(totals)
        grouped = self._read_group_by_partner('before_period')
        return {partner_id: values['balance'] for partner_id, values in grouped.items()}

    def _partner_ids_from_totals(self, period_totals, initial_totals, selected_ids):
        if selected_ids:
            return selected_ids
        rounding = self.currency.rounding
        partner_ids = set(period_totals)
        for partner_id, balance in initial_totals.items():
            if not float_is_zero(balance, precision_rounding=rounding):
                partner_ids.add(partner_id)
        return sorted(partner_ids, key=lambda pid: (pid is False, pid or 0))

    def _batch_extra_children(self, partners, include_details):
        if 'opal.partner.ledger.hook' not in self.env:
            return {}
        if not include_details and not self.options.get('show_opal_balance'):
            return {}
        hook = self.env['opal.partner.ledger.hook']
        if hasattr(hook, 'get_partners_children_map'):
            return hook.get_partners_children_map(partners, self.options, self.currency)
        return {
            (partner.id if partner else False): hook.get_partner_children(
                partner, self.options, self.currency
            )
            for partner in partners
        }

    def _get_partner_ids(self):
        selected = self._selected_partner_ids()
        if selected:
            return selected
        period_totals = self._read_group_by_partner('period')
        initial_totals = self._initial_totals_by_partner()
        return self._partner_ids_from_totals(period_totals, initial_totals, selected)

    def _inferred_partner_id(self, line):
        if line.partner_id:
            return line.partner_id.id
        move = line.move_id
        if 'ages_project_id' in move._fields and move.ages_project_id and move.ages_project_id.partner_id:
            return move.ages_project_id.partner_id.id
        if (
            'ages_analytic_account_id' in move._fields
            and move.ages_analytic_account_id
            and move.ages_analytic_account_id.partner_id
        ):
            return move.ages_analytic_account_id.partner_id.id
        return False

    def _inferred_partner_ids(self, lines):
        return {
            partner_id
            for partner_id in (self._inferred_partner_id(line) for line in lines)
            if partner_id
        }

    def _browse_partners(self, partner_ids):
        real_ids = [pid for pid in partner_ids if pid]
        partners = self.env['res.partner'].browse(real_ids).sorted(key=lambda p: p.name or '')
        result = list(partners)
        if False in partner_ids or None in partner_ids:
            result.append(False)
        return result

    def _partner_name(self, partner):
        if partner:
            return partner.display_name
        return 'Unknown Partner'

    def _partner_line_domain(self, partner):
        if partner:
            return partner_reach_domain(self.env, [partner.id])
        domain = [('partner_id', '=', False)]
        Move = self.env['account.move']
        if 'ages_project_id' in Move._fields:
            domain = expression.AND([domain, [
                '|',
                ('move_id.ages_project_id', '=', False),
                ('move_id.ages_project_id.partner_id', '=', False),
            ]])
        return domain

    def _get_initial_balance(self, partner):
        if not self.date_from:
            return 0.0
        domain = expression.AND([
            self._base_domain(date_scope='before_period'),
            self._partner_line_domain(partner),
        ])
        groups = self.env['account.move.line'].read_group(
            domain, ['balance:sum'], [], lazy=False
        )
        return groups[0]['balance'] if groups else 0.0

    def _get_move_lines(self, partner):
        domain = expression.AND([
            self._base_domain(date_scope='period'),
            self._partner_line_domain(partner),
        ])
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

    def _unique_or_blank(self, values):
        unique = {value for value in values if value}
        if len(unique) == 1:
            return unique.pop()
        return False

    def _grouped_move_rows(self, move_lines):
        """One partner-ledger row per journal entry, not per journal item."""
        grouped = []
        index = {}
        for move_line in move_lines:
            move_id = move_line.move_id.id
            bucket = index.get(move_id)
            if not bucket:
                bucket = {
                    'move': move_line.move_id,
                    'line_ids': [],
                }
                index[move_id] = bucket
                grouped.append(bucket)
            bucket['line_ids'].append(move_line.id)
        Line = self.env['account.move.line']
        for bucket in grouped:
            bucket['lines'] = Line.browse(bucket['line_ids'])
        return grouped

    def _merged_move_communication(self, move, lines):
        ref = (move.ref or '').strip()
        move_name = (move.name or '').strip()
        if ref and ref != move_name:
            return ref
        return False

    def _merged_move_child(self, partner_id, move, lines, running_balance):
        debit = self.currency.round(sum(lines.mapped('debit')))
        credit = self.currency.round(sum(lines.mapped('credit')))
        running_balance = self.currency.round(running_balance + sum(lines.mapped('balance')))
        currencies = lines.mapped('currency_id').filtered(lambda currency: currency != self.currency)
        amount_currency = False
        currency_name = False
        if len(currencies) == 1:
            currency_name = currencies.name
            amount_currency = sum(lines.mapped('amount_currency'))
        due_dates = [line.date_maturity for line in lines if line.date_maturity]
        analytic_names = [self._line_project_name(line) for line in lines]
        first = lines[:1]
        return {
            'id': f'move_{move.id}',
            'name': move.name or first.move_name or '',
            'level': 1,
            'line_type': 'move_line',
            'foldable': False,
            'partner_id': partner_id,
            'move_line_id': first.id,
            'move_id': move.id,
            'journal_code': self._unique_or_blank(lines.mapped('journal_id').mapped('code')),
            'account_code': self._unique_or_blank(lines.mapped('account_id').mapped('code')),
            'analytic_name': self._unique_or_blank(analytic_names) or '',
            'date': fields.Date.to_string(move.date or first.date),
            'due_date': fields.Date.to_string(max(due_dates)) if due_dates else False,
            'matching_number': self._unique_or_blank(lines.mapped('matching_number')),
            'communication': self._merged_move_communication(move, lines),
            'amount_currency': amount_currency if currency_name else False,
            'currency_name': currency_name,
            'debit': debit,
            'credit': credit,
            'balance': running_balance,
            'children': [],
        }, running_balance

    def _iter_merged_move_children(self, partner_id, move, lines, running_balance):
        """Yield one or more ledger rows for a journal entry. Other modules may split rows."""
        child, running_balance = self._merged_move_child(
            partner_id, move, lines, running_balance
        )
        yield child, running_balance

    def _build_partner_line(
        self,
        partner,
        include_details=False,
        move_lines=None,
        initial_balance=None,
        extra_children=None,
        period_debit=None,
        period_credit=None,
        period_balance=None,
    ):
        load_lines = move_lines is None
        if initial_balance is None:
            initial_balance = self._get_initial_balance(partner)
        if load_lines:
            move_lines = self._get_move_lines(partner)
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
        has_extra = bool(extra_children)
        keep_opal = bool(self.options.get('show_opal_balance'))

        if (
            float_is_zero(period_debit, precision_rounding=rounding)
            and float_is_zero(period_credit, precision_rounding=rounding)
            and float_is_zero(initial_balance, precision_rounding=rounding)
            and not has_extra
            and not keep_opal
        ):
            return None

        partner_id = partner.id if partner else False
        children = []
        if include_details:
            if self.date_from:
                children.append({
                    'id': f'partner_{partner_id or "none"}_initial',
                    'name': 'Initial Balance',
                    'level': 1,
                    'line_type': 'initial',
                    'foldable': False,
                    'partner_id': partner_id,
                    'journal_code': False,
                    'account_code': False,
                    'analytic_name': '',
                    'date': False,
                    'due_date': False,
                    'matching_number': False,
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
                children.extend(self._extra_children_after_initial(partner, initial_balance))

            running_balance = initial_balance
            for bucket in self._grouped_move_rows(move_lines):
                for child, running_balance in self._iter_merged_move_children(
                    partner_id, bucket['move'], bucket['lines'], running_balance
                ):
                    children.append(child)
        elif extra_children:
            children.extend(extra_children)

        has_details = (
            not float_is_zero(period_debit, precision_rounding=rounding)
            or not float_is_zero(period_credit, precision_rounding=rounding)
            or (
                self.date_from
                and not float_is_zero(initial_balance, precision_rounding=rounding)
            )
            or has_extra
            or keep_opal
        )

        line = {
            'id': f'partner_{partner_id or "none"}',
            'name': self._partner_name(partner),
            'level': 0,
            'line_type': 'partner',
            'foldable': has_details,
            'partner_id': partner_id,
            'journal_code': False,
            'account_code': False,
            'analytic_name': '',
            'date': False,
            'due_date': False,
            'matching_number': False,
            'amount_currency': False,
            'currency_name': False,
            'debit': period_debit,
            'credit': period_credit,
            'balance': ending_balance,
            'children': children,
        }
        if keep_opal and 'opal.partner.ledger.hook' in self.env:
            hook = self.env['opal.partner.ledger.hook']
            if hasattr(hook, 'adjust_partner_line'):
                hook.adjust_partner_line(line, extra_children, self.options, self.currency)
        return line

    def _extra_children_after_initial(self, partner, initial_balance):
        if 'opal.partner.ledger.hook' not in self.env:
            return []
        return self.env['opal.partner.ledger.hook'].get_partner_children(
            partner, self.options, self.currency
        )

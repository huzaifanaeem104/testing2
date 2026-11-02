# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields
from odoo.osv import expression
from odoo.tools.float_utils import float_is_zero


class ProjectCashLedgerMixin:
    """Posted journal items that show mobilization / retention cash movement."""

    special_account_fname = False
    payment_move_link_fname = False
    source_model = False
    source_contract_field = 'contract_id'
    warning_label = 'special'

    def _special_account(self):
        if not self.special_account_fname:
            return self.env['account.account']
        account = getattr(self.company, self.special_account_fname, False)
        return account or self.env['account.account']

    def _ledger_warning(self):
        if self._special_account():
            return []
        return [
            f'Configure the {self.warning_label} account in Project → Configuration → Settings '
            'to show debit / credit journal items.'
        ]

    def _aml_state_domain(self):
        if self.confirmed_only:
            return [('parent_state', '=', 'posted')]
        return [('parent_state', '!=', 'cancel')]

    def _aml_date_domain(self, date_scope='as_of'):
        domain = []
        if date_scope == 'as_of':
            domain.append(('date', '<=', self.date_to))
        elif date_scope == 'period':
            if self.date_from:
                domain.append(('date', '>=', self.date_from))
            domain.append(('date', '<=', self.date_to))
        return domain

    def _aml_base_domain(self, date_scope='as_of'):
        company_ids = self.options.get('company_ids') or [self.company.id]
        return (
            [
                ('company_id', 'in', company_ids),
                ('display_type', 'not in', ('line_section', 'line_note')),
            ]
            + self._aml_state_domain()
            + self._aml_date_domain(date_scope)
        )

    def _search_ledger_amls(self, contract_ids, date_scope='as_of'):
        move_line = self.env['account.move.line']
        if not contract_ids:
            return move_line
        Move = self.env['account.move']
        base = self._aml_base_domain(date_scope)
        domains = []
        account = self._special_account()
        if account and 'ages_contract_id' in Move._fields:
            domains.append(expression.AND([base, [
                ('account_id', '=', account.id),
                ('move_id.ages_contract_id', 'in', list(contract_ids)),
            ]]))
        link = self.payment_move_link_fname
        if (
            link
            and self.source_model
            and link in Move._fields
            and self.source_model in self.env
        ):
            Source = self.env[self.source_model]
            source_domain = [
                (self.source_contract_field, 'in', list(contract_ids)),
            ]
            if 'state' in Source._fields:
                source_domain.append(('state', '!=', 'cancelled'))
            if 'company_id' in Source._fields:
                source_domain.append((
                    'company_id', 'in',
                    self.options.get('company_ids') or [self.company.id],
                ))
            sources = Source.search(source_domain)
            if sources:
                domains.append(expression.AND([base, [
                    (f'move_id.{link}', 'in', sources.ids),
                ]]))
                Payment = self.env['account.payment']
                if link in Payment._fields:
                    payments = Payment.search([(link, 'in', sources.ids)])
                    payment_move_ids = payments.mapped('move_id').ids
                    if payment_move_ids:
                        domains.append(expression.AND([base, [
                            ('move_id', 'in', payment_move_ids),
                        ]]))
        if not domains:
            return move_line
        return move_line.search(expression.OR(domains), order='date, move_name, id')

    def _contract_id_for_aml(self, aml):
        move = aml.move_id
        if 'ages_contract_id' in move._fields and move.ages_contract_id:
            return move.ages_contract_id.id
        link = self.payment_move_link_fname
        if link and link in move._fields and move[link]:
            source = move[link]
            if source and self.source_contract_field in source._fields and source[self.source_contract_field]:
                return source[self.source_contract_field].id
        return False

    def _group_amls_by_contract(self, amls):
        grouped = defaultdict(lambda: self.env['account.move.line'])
        for aml in amls:
            contract_id = self._contract_id_for_aml(aml)
            if contract_id:
                grouped[contract_id] |= aml
        return grouped

    def _is_special_account_line(self, aml):
        account = self._special_account()
        if not account:
            return True
        return aml.account_id.id == account.id

    def _special_amls(self, amls):
        if not self._special_account():
            return amls
        return amls.filtered(self._is_special_account_line)

    def _split_amls(self, amls):
        opening = self.env['account.move.line']
        period = self.env['account.move.line']
        for aml in amls:
            if self.date_from and aml.date and aml.date < self.date_from:
                opening |= aml
            else:
                period |= aml
        return opening, period

    def _running_bill(self, aml):
        move = aml.move_id
        if 'ages_running_bill_id' in move._fields:
            return move.ages_running_bill_id
        return False

    def _running_bill_name(self, aml):
        if not self._is_special_account_line(aml):
            return False
        bill = self._running_bill(aml)
        if not bill:
            return False
        return bill.display_name or bill.name or False

    def _aml_label(self, aml):
        move_name = aml.move_name or aml.move_id.display_name or ''
        label = aml.name or ''
        if label and move_name and label != move_name:
            return f"{move_name} — {label}"
        return move_name or label or 'Journal Item'

    def _tax_entry_account_ids(self):
        cached = getattr(self, '_cached_tax_entry_account_ids', None)
        if cached is not None:
            return cached
        ids = set()
        company = getattr(self, 'company', None) or self.env.company
        if (
            'withholding_tax_base_account_id' in company._fields
            and company.withholding_tax_base_account_id
        ):
            ids.add(company.withholding_tax_base_account_id.id)
        Tax = self.env['account.tax']
        company_ids = (
            getattr(self, 'options', {}) or {}
        ).get('company_ids') or [company.id]
        domain = [('company_id', 'in', company_ids)]
        if 'is_withholding_tax_on_payment' in Tax._fields:
            domain.append(('is_withholding_tax_on_payment', '=', True))
            taxes = Tax.with_context(active_test=False).search(domain)
        else:
            taxes = Tax.browse()
        for tax in taxes:
            reps = tax.invoice_repartition_line_ids | tax.refund_repartition_line_ids
            if 'repartition_line_ids' in tax._fields:
                reps |= tax.repartition_line_ids
            for line in reps.filtered(lambda rec: rec.repartition_type == 'tax' and rec.account_id):
                ids.add(line.account_id.id)
            group = tax.tax_group_id
            if group:
                if group.tax_receivable_account_id:
                    ids.add(group.tax_receivable_account_id.id)
                if group.tax_payable_account_id:
                    ids.add(group.tax_payable_account_id.id)
        self._cached_tax_entry_account_ids = ids
        return ids

    def _is_tax_entry(self, aml):
        if aml.tax_line_id or aml.tax_repartition_line_id:
            return True
        name = (aml.name or '').strip().upper()
        if (
            name.startswith('WTH TAX')
            or name.startswith('WH TAX')
            or name.startswith('WHT')
            or name.startswith('WH BASE')
            or 'WITHHOLDING TAX' in name
        ):
            return True
        return bool(aml.account_id and aml.account_id.id in self._tax_entry_account_ids())

    def _aml_badge(self, aml):
        if self._running_bill_name(aml):
            return 'Running Bill'
        move = aml.move_id
        if move.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
            return 'Invoice'
        if (
            ('origin_payment_id' in move._fields and move.origin_payment_id)
            or ('payment_id' in move._fields and move.payment_id)
            or ('payment_id' in aml._fields and aml.payment_id)
        ):
            return 'Payment'
        link = self.payment_move_link_fname
        if link and link in move._fields and move[link]:
            return 'Payment'
        return 'Entry'

    def _aml_ledger_amounts(self, amls):
        debit = self._round(sum(amls.mapped('debit')))
        credit = self._round(sum(amls.mapped('credit')))
        return {
            'debit': debit,
            'credit': credit,
            'balance': self._round(debit - credit),
        }

    def _account_vals(self, account=None):
        account = account if account is not None else self._special_account()
        if not account:
            return {
                'account_id': False,
                'account_code': '',
                'account_name': '',
            }
        return {
            'account_id': account.id,
            'account_code': account.code or '',
            'account_name': account.display_name or '',
        }

    def _build_opening_line(self, contract, amounts):
        return self._amount_line(
            line_id=f'opening_{contract.id}',
            name='Initial Balance',
            line_type='initial',
            level=2,
            foldable=False,
            amounts=amounts,
            extra={
                'partner_id': contract.partner_id.id if contract.partner_id else False,
                'contract_id': contract.id,
                'project_id': contract.project_id.id if contract.project_id else False,
                'date': fields.Date.to_string(self.date_from) if self.date_from else False,
                **self._account_vals(),
            },
        )

    def _build_move_line_rows(self, contract, amls, start_balance=0.0):
        lines = []
        running = start_balance
        for aml in amls:
            is_tax_entry = self._is_tax_entry(aml)
            debit = self._round(aml.debit or 0.0)
            credit = self._round(aml.credit or 0.0)
            if self._is_special_account_line(aml):
                running = self._round(running + (aml.balance or 0.0))
            account = aml.account_id
            lines.append(self._amount_line(
                line_id=f'aml_{aml.id}',
                name=self._aml_label(aml),
                line_type='move_line',
                level=2,
                foldable=False,
                amounts={
                    'debit': debit,
                    'credit': credit,
                    'balance': running,
                },
                extra={
                    'partner_id': contract.partner_id.id if contract.partner_id else False,
                    'contract_id': contract.id,
                    'project_id': contract.project_id.id if contract.project_id else False,
                    'move_id': aml.move_id.id,
                    'move_line_id': aml.id,
                    'journal_code': aml.journal_id.code if aml.journal_id else '',
                    'date': fields.Date.to_string(aml.date) if aml.date else False,
                    'badge': self._aml_badge(aml),
                    'running_bill_name': self._running_bill_name(aml),
                    'is_tax_entry': is_tax_entry,
                    **self._account_vals(account),
                },
            ))
        return lines


class ProjectCashLedgerEngine(ProjectCashLedgerMixin):
    """Client → contract fold with debit / credit journal-item detail."""

    date_label_fields = ('date_from', 'date_to')
    percent_field = False
    percent_key = 'percent'

    def __init__(self, env, options):
        self.env = env
        self.company = env.company
        self.currency = self.company.currency_id
        self.options = options
        self.date_from = (
            fields.Date.to_date(options['date_from'])
            if options.get('date_from') else None
        )
        self.date_to = (
            fields.Date.to_date(options['date_to'])
            if options.get('date_to')
            else fields.Date.context_today(env)
        )
        self.confirmed_only = options.get('confirmed_only', True)
        self.show_zero_lines = options.get('show_zero_lines', False)
        self.hide_tax_entries = bool(options.get('hide_tax_entries'))
        self._amls_by_contract = {}
        self._cached_tax_entry_account_ids = None

    def get_report_data(self):
        contracts = self._get_contracts()
        aggregates = self._aggregate_contracts(contracts)
        grouped = defaultdict(list)
        for contract in contracts:
            totals = aggregates.get(contract.id)
            if not totals:
                continue
            grouped[contract.partner_id.id if contract.partner_id else False].append(
                (contract, totals)
            )

        include_details = self.options.get('unfold_all', False)
        lines = []
        totals = self._empty_amounts()
        for partner_id in self._sorted_partner_ids(grouped):
            partner_contracts = grouped[partner_id]
            partner = partner_contracts[0][0].partner_id
            line = self._build_client_line(
                partner, partner_contracts, include_details=include_details
            )
            if line:
                lines.append(line)
                self._add_amounts(totals, line)

        lines.append(self._amount_line(
            line_id='total',
            name='Total',
            line_type='total',
            level=0,
            foldable=False,
            amounts=totals,
            extra=self._account_vals(),
        ))

        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self.currency.symbol,
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'warnings': self._ledger_warning(),
        }

    def get_client_detail(self, partner_id):
        contracts = self._get_contracts().filtered(
            lambda contract: (contract.partner_id.id if contract.partner_id else False) == (partner_id or False)
        )
        aggregates = self._aggregate_contracts(contracts)
        partner_contracts = [
            (contract, aggregates[contract.id])
            for contract in contracts
            if contract.id in aggregates
        ]
        partner = contracts[:1].partner_id if contracts else self.env['res.partner']
        line = self._build_client_line(partner, partner_contracts, include_details=True)
        return {'children': line.get('children') or [] if line else []}

    def flatten_lines(self, lines=None, unfolded_ids=None):
        unfolded_ids = set(unfolded_ids or [])
        unfold_all = self.options.get('unfold_all', False)
        result = []

        def _walk(node):
            if self.hide_tax_entries and node.get('is_tax_entry'):
                return
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
        return f"As of {fields.Date.to_string(self.date_to)}"

    def _empty_amounts(self):
        return {
            'debit': 0.0,
            'credit': 0.0,
            'balance': 0.0,
        }

    def _add_amounts(self, target, source):
        for key in self._empty_amounts():
            target[key] += source.get(key, 0.0) or 0.0

    def _round(self, amount):
        return self.currency.round(amount or 0.0)

    def _is_zero_amounts(self, amounts):
        rounding = self.currency.rounding
        return all(
            float_is_zero(amounts.get(key, 0.0) or 0.0, precision_rounding=rounding)
            for key in self._empty_amounts()
        )

    def _contract_domain(self):
        domain = [(
            'company_id', 'in',
            self.options.get('company_ids') or [self.company.id],
        )]
        partner_ids = self.options.get('partner_ids') or []
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        project_ids = self.options.get('project_ids') or []
        if project_ids or self.options.get('project_scope_applied'):
            domain.append(('project_id', 'in', project_ids or [0]))
        contract_ids = self.options.get('contract_ids') or []
        if contract_ids:
            domain.append(('id', 'in', contract_ids))
        sub_company_ids = self.options.get('sub_company_ids') or []
        if sub_company_ids:
            assigned_ids = [sub_id for sub_id in sub_company_ids if sub_id]
            if assigned_ids and 0 in sub_company_ids:
                domain += [
                    '|',
                    ('sub_company_id', 'in', assigned_ids),
                    ('sub_company_id', '=', False),
                ]
            elif assigned_ids:
                domain.append(('sub_company_id', 'in', assigned_ids))
            elif 0 in sub_company_ids:
                domain.append(('sub_company_id', '=', False))
        contract_state = self.options.get('contract_state') or 'all'
        if contract_state and contract_state != 'all':
            domain.append(('state', '=', contract_state))
        return domain

    def _get_contracts(self):
        return self.env['ages.contract'].search(
            self._contract_domain(),
            order='partner_id, name, id',
        )

    def _aggregate_contracts(self, contracts):
        self._amls_by_contract = {}
        result = {}
        if not contracts:
            return result
        amls = self._search_ledger_amls(contracts.ids, date_scope='as_of')
        grouped = self._group_amls_by_contract(amls)
        self._amls_by_contract = grouped
        for contract in contracts:
            contract_amls = grouped.get(contract.id, self.env['account.move.line'])
            amounts = self._aml_ledger_amounts(self._special_amls(contract_amls))
            if contract_amls or self.show_zero_lines:
                result[contract.id] = amounts
        return result

    def _sorted_partner_ids(self, grouped):
        partners = self.env['res.partner'].browse([
            partner_id for partner_id in grouped if partner_id
        ]).sorted(key=lambda partner: partner.name or '')
        ordered = [partner.id for partner in partners]
        if False in grouped:
            ordered.append(False)
        return ordered

    def _build_client_line(self, partner, partner_contracts, include_details=False):
        totals = self._empty_amounts()
        children = []
        for contract, amounts in partner_contracts:
            self._add_amounts(totals, amounts)
            if include_details:
                children.append(self._build_contract_line(contract, amounts))

        if not partner_contracts:
            return None
        if not include_details and not self.show_zero_lines and self._is_zero_amounts(totals):
            return None

        partner_id = partner.id if partner else False
        for key in totals:
            totals[key] = self._round(totals[key])
        return self._amount_line(
            line_id=f'client_{partner_id or "none"}',
            name=partner.display_name if partner else 'Unknown Client',
            line_type='client',
            level=0,
            foldable=True,
            amounts=totals,
            extra={
                'partner_id': partner_id,
                'children': children,
                **self._account_vals(),
            },
        )

    def _contract_percent(self, contract):
        if self.percent_field and self.percent_field in contract._fields:
            return contract[self.percent_field] or 0.0
        return 0.0

    def _build_contract_line(self, contract, amounts):
        contract_amls = self._amls_by_contract.get(
            contract.id, self.env['account.move.line']
        )
        opening_amls, period_amls = self._split_amls(contract_amls)
        opening_amounts = self._aml_ledger_amounts(self._special_amls(opening_amls))
        children = []
        if self.date_from and (
            self.show_zero_lines or not self._is_zero_amounts(opening_amounts)
        ):
            children.append(self._build_opening_line(contract, opening_amounts))
        children.extend(self._build_move_line_rows(
            contract, period_amls, start_balance=opening_amounts['balance']
        ))
        name = contract.display_name or contract.name
        if contract.project_id:
            name = f"{name} — {contract.project_id.display_name}"
        extra = {
            'partner_id': contract.partner_id.id if contract.partner_id else False,
            'contract_id': contract.id,
            'project_id': contract.project_id.id if contract.project_id else False,
            'contract_state': contract.state,
            'children': children,
            **self._account_vals(),
        }
        extra[self.percent_key] = self._contract_percent(contract)
        return self._amount_line(
            line_id=f'contract_{contract.id}',
            name=name,
            line_type='contract',
            level=1,
            foldable=bool(children),
            amounts=amounts,
            extra=extra,
        )

    def _amount_line(self, line_id, name, line_type, level, foldable, amounts, extra=None):
        line = {
            'id': line_id,
            'name': name,
            'level': level,
            'line_type': line_type,
            'foldable': foldable,
            'partner_id': False,
            'contract_id': False,
            'project_id': False,
            'move_id': False,
            'move_line_id': False,
            'account_id': False,
            'account_code': '',
            'account_name': '',
            'journal_code': '',
            'badge': False,
            'running_bill_name': False,
            'is_tax_entry': False,
            'contract_state': False,
            'date': False,
            'debit': amounts.get('debit', 0.0) or 0.0,
            'credit': amounts.get('credit', 0.0) or 0.0,
            'balance': amounts.get('balance', 0.0) or 0.0,
            'children': [],
        }
        line[self.percent_key] = False
        if extra:
            line.update(extra)
        return line

# -*- coding: utf-8 -*-

import re

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_internal_transfer = fields.Boolean(
        string='Internal Transfer',
        default=False,
        copy=False,
        help='A journal entry will be created using Payment Details (destination journals / projects).',
    )
    is_vendors_transfer = fields.Boolean(
        string='Vendors Transfer',
        default=False,
        copy=False,
        help='Pay several vendors from one cash/bank payment. Each Payment Details line debits that vendor.',
    )
    description = fields.Text(
        string='Description',
        help='Description for internal transfer payment',
    )
    internal_transfer_description = fields.Text(
        string='Payment Description',
        related='description',
        readonly=False,
    )
    payment_detail_line_ids = fields.One2many(
        comodel_name='account.payment.detail.line',
        inverse_name='payment_id',
        string='Payment Details',
        copy=True,
    )
    # Kept for backward compatibility; for internal transfers use detail lines instead.
    destination_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Destination Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('id', '!=', journal_id)]",
        copy=False,
        check_company=True,
    )

    ages_sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        required=False,
        copy=True,
        index=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    ages_contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        copy=True,
        index=True,
    )
    ages_project_wise_contract = fields.Char(
        related='ages_contract_id.project_wise_name',
        string='Project-Wise Contract',
        readonly=True,
        related_sudo=True,
    )
    ages_contract_description = fields.Text(
        related='ages_contract_id.contract_description',
        string='Contract Description',
        readonly=True,
        related_sudo=True,
    )
    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        copy=True,
        index=True,
        check_company=True,
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        copy=True,
        index=True,
        check_company=True,
    )
    ages_apply_100_payment_analytic = fields.Boolean(
        string='Apply 100% Payment Analytic Distribution',
        default=False,
        copy=True,
        help='When enabled, the selected Analytic Account is applied at 100% '
             'on the credit (selected journal) line. When disabled, that journal '
             'line is posted without payment analytic.',
    )
    ages_payment_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        copy=True,
        index=True,
        check_company=True,
        help='Applied at 100% on the payment/liquidity journal item when '
             'Apply 100% Payment Analytic Distribution is enabled.',
    )
    ages_running_bill_id = fields.Many2one(
        comodel_name='ages.running.bill',
        string='Running Bill',
        copy=False,
        index=True,
        readonly=True,
    )
    ages_mobilization_advance_id = fields.Many2one(
        comodel_name='ages.mobilization.advance',
        string='Mobilization Advance',
        copy=False,
        index=True,
        readonly=True,
    )
    ages_retention_recovery_id = fields.Many2one(
        comodel_name='ages.retention.recovery',
        string='Retention Receive',
        copy=False,
        index=True,
        readonly=True,
    )

    def _ages_sync_linked_documents_from_reconciled(self):
        """Fill linked AGES docs from reconciled invoices when missing (later reconcile)."""
        for payment in self:
            moves = payment.reconciled_invoice_ids | payment.reconciled_bill_ids
            if not moves:
                continue
            vals = {}
            if not payment.ages_running_bill_id:
                bills = moves.mapped('ages_running_bill_id')
                if bills:
                    vals['ages_running_bill_id'] = bills[0].id
            if not payment.ages_mobilization_advance_id:
                mobs = moves.mapped('ages_mobilization_advance_id')
                if mobs:
                    vals['ages_mobilization_advance_id'] = mobs[0].id
            if not payment.ages_retention_recovery_id:
                rets = moves.mapped('ages_retention_recovery_id')
                if rets:
                    vals['ages_retention_recovery_id'] = rets[0].id
            if not payment.ages_sub_company_id:
                subs = moves.mapped('ages_sub_company_id')
                if len(subs) == 1:
                    vals['ages_sub_company_id'] = subs.id
            if not payment.ages_contract_id:
                contracts = moves.mapped('ages_contract_id')
                if len(contracts) == 1:
                    vals['ages_contract_id'] = contracts.id
                elif not payment.ages_project_id:
                    projects = moves.mapped('ages_project_id')
                    if len(projects) == 1 and projects.ages_contract_id:
                        vals['ages_contract_id'] = projects.ages_contract_id.id
            if not payment.ages_project_id:
                projects = moves.mapped('ages_project_id')
                if len(projects) == 1:
                    vals['ages_project_id'] = projects.id
            if not payment.ages_analytic_account_id:
                analytics = moves.mapped('ages_analytic_account_id')
                if len(analytics) == 1:
                    vals['ages_analytic_account_id'] = analytics.id
                elif payment.ages_project_id and payment.ages_project_id.account_id:
                    vals['ages_analytic_account_id'] = payment.ages_project_id.account_id.id
                elif vals.get('ages_project_id'):
                    project = self.env['project.project'].browse(vals['ages_project_id'])
                    if project.account_id:
                        vals['ages_analytic_account_id'] = project.account_id.id
            if vals:
                payment.write(vals)

    @api.onchange('ages_sub_company_id')
    def _onchange_ages_sub_company_id(self):
        domain = self._ages_project_domain()
        if (
            self.ages_project_id
            and self.ages_sub_company_id
            and not self._ages_project_belongs_to_sub_company(
                self.ages_project_id, self.ages_sub_company_id
            )
        ):
            self.ages_project_id = False
            self.ages_analytic_account_id = False
        return {'domain': {'ages_project_id': domain}}

    @api.onchange('ages_contract_id')
    def _onchange_ages_contract_id(self):
        if self.ages_contract_id:
            contract = self.ages_contract_id
            if contract.project_id:
                self.ages_project_id = contract.project_id
            if contract.analytic_account_id:
                self.ages_analytic_account_id = contract.analytic_account_id
            elif contract.project_id.account_id:
                self.ages_analytic_account_id = contract.project_id.account_id
            if contract.sub_company_id:
                self.ages_sub_company_id = contract.sub_company_id

    @api.onchange('ages_project_id')
    def _onchange_ages_project_id(self):
        """Project fills analytic and Active Company. Contract stays manual."""
        if self.ages_project_id:
            self.ages_analytic_account_id = self.ages_project_id.account_id
            sub_company = self._ages_sub_company_from_project(self.ages_project_id)
            if sub_company:
                self.ages_sub_company_id = sub_company
            contract = self.ages_contract_id
            if contract and contract.project_id and contract.project_id != self.ages_project_id:
                self.ages_contract_id = False
        else:
            self.ages_analytic_account_id = False

    @api.onchange('is_internal_transfer')
    def _onchange_is_internal_transfer(self):
        if self.is_internal_transfer:
            self.is_vendors_transfer = False
        elif not self.is_vendors_transfer:
            self.ages_apply_100_payment_analytic = False
            self.ages_payment_analytic_account_id = False

    @api.onchange('is_vendors_transfer')
    def _onchange_is_vendors_transfer(self):
        if self.is_vendors_transfer:
            self.is_internal_transfer = False
            self.partner_id = False
            self.partner_type = 'supplier'
            self.payment_type = 'outbound'
            self.ages_project_id = False
            self.ages_analytic_account_id = False
            if self.payment_detail_line_ids:
                self.amount = sum(self.payment_detail_line_ids.mapped('amount'))
        elif not self.is_internal_transfer:
            self.ages_apply_100_payment_analytic = False
            self.ages_payment_analytic_account_id = False

    @api.onchange('ages_apply_100_payment_analytic')
    def _onchange_ages_apply_100_payment_analytic(self):
        if not self.ages_apply_100_payment_analytic:
            self.ages_payment_analytic_account_id = False

    @api.constrains('is_internal_transfer', 'is_vendors_transfer')
    def _check_ages_transfer_modes(self):
        for payment in self:
            if payment.is_internal_transfer and payment.is_vendors_transfer:
                raise ValidationError(_(
                    'Internal Transfer and Vendors Transfer cannot be used together.'
                ))

    def _ages_uses_payment_details(self):
        self.ensure_one()
        return self.is_internal_transfer or self.is_vendors_transfer

    def _ages_sync_detail_amount(self):
        for payment in self:
            if not payment._ages_uses_payment_details() or not payment.payment_detail_line_ids:
                continue
            total = sum(payment.payment_detail_line_ids.mapped('amount'))
            if abs(payment.amount - total) > 0.00001:
                super(AccountPayment, payment).write({'amount': total})

    def _ages_project_domain(self):
        self.ensure_one()
        domain = []
        if self.company_id:
            domain.append(('company_id', 'in', [self.company_id.id, False]))
        if self.ages_sub_company_id:
            domain.append(('ages_contract_id.sub_company_id', '=', self.ages_sub_company_id.id))
        return domain

    def _ages_sub_company_from_project(self, project):
        """Active Company the project was opened on, if set."""
        if not project:
            return self.env['ages.sub.company']
        project = project.sudo()
        if 'ages_sub_company_id' in project._fields and project.ages_sub_company_id:
            return project.ages_sub_company_id
        contract = project.ages_contract_id if 'ages_contract_id' in project._fields else False
        if contract and contract.sub_company_id:
            return contract.sub_company_id
        return self.env['ages.sub.company']

    def _ages_project_belongs_to_sub_company(self, project, sub_company):
        if not project or not sub_company:
            return True
        project = project.sudo()
        if 'ages_sub_company_id' in project._fields and project.ages_sub_company_id:
            return project.ages_sub_company_id == sub_company
        contract = project.ages_contract_id if 'ages_contract_id' in project._fields else False
        if contract and contract.sub_company_id:
            return contract.sub_company_id == sub_company
        return True

    def _ages_analytic_distribution(self):
        """Header-level analytic (non internal-transfer payments)."""
        self.ensure_one()
        if not self.ages_analytic_account_id:
            return False
        return {str(self.ages_analytic_account_id.id): 100.0}

    def _ages_payment_liquidity_analytic_distribution(self):
        """100% analytic for the payment/liquidity journal item only."""
        self.ensure_one()
        if (
            self.ages_apply_100_payment_analytic
            and self.ages_payment_analytic_account_id
        ):
            return {str(self.ages_payment_analytic_account_id.id): 100.0}
        return False

    def _ages_validate_payment_liquidity_analytic(self):
        self.ensure_one()
        if (
            self.ages_apply_100_payment_analytic
            and not self.ages_payment_analytic_account_id
        ):
            raise UserError(_(
                'Select an Analytic Account for 100% payment analytic distribution.'
            ))

    def _ages_source_analytic_distribution_from_details(self):
        """
        Analytic distribution for the source journal account line,
        weighted by payment detail amounts. Percentages sum to 100.
        """
        self.ensure_one()
        totals = {}
        total_amount = sum(self.payment_detail_line_ids.mapped('amount'))
        if total_amount <= 0:
            return False

        for line in self.payment_detail_line_ids:
            dist = line.analytic_distribution or {}
            if dist:
                for account_key, percent in dist.items():
                    account_id = int(str(account_key).split(',')[0])
                    totals[account_id] = totals.get(account_id, 0.0) + line.amount * (float(percent) / 100.0)
                continue
            aa = line.ages_analytic_account_id
            if not aa:
                continue
            totals[aa.id] = totals.get(aa.id, 0.0) + line.amount

        if not totals:
            return False

        dist = {}
        running = 0.0
        items = list(totals.items())
        for idx, (aa_id, amount) in enumerate(items):
            if idx == len(items) - 1:
                pct = round(100.0 - running, 6)
            else:
                pct = round((amount / total_amount) * 100.0, 6)
                running += pct
            if pct:
                dist[str(aa_id)] = pct
        return dist or False

    def _ages_mob_retention_counterpart_account(self):
        """Counterpart account for direct mobilization / retention receive payments."""
        self.ensure_one()
        if self.ages_mobilization_advance_id:
            return self.company_id.ages_mobilization_account_id
        if self.ages_retention_recovery_id:
            return self.company_id.ages_retention_account_id
        return self.env['account.account']

    @api.depends(
        'journal_id', 'partner_id', 'partner_type',
        'ages_mobilization_advance_id', 'ages_retention_recovery_id',
    )
    def _compute_destination_account_id(self):
        super()._compute_destination_account_id()
        for pay in self:
            counterpart = pay._ages_mob_retention_counterpart_account()
            if counterpart:
                pay.destination_account_id = counterpart

    def _prepare_move_liquidity_lines(self, default_values):
        lines = super()._prepare_move_liquidity_lines(default_values)
        payment_dist = self._ages_payment_liquidity_analytic_distribution()
        if payment_dist:
            for vals in lines:
                vals['analytic_distribution'] = payment_dist
        return lines

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        line_vals_list = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
        )
        dist = self._ages_analytic_distribution()
        payment_dist = self._ages_payment_liquidity_analytic_distribution()
        counterpart = self._ages_mob_retention_counterpart_account()
        liquidity = self._ages_liquidity_account()
        for vals in line_vals_list:
            is_liquidity = bool(liquidity) and vals.get('account_id') == liquidity.id
            if is_liquidity and payment_dist:
                vals['analytic_distribution'] = payment_dist
            elif dist:
                vals['analytic_distribution'] = dist
            if not counterpart or not liquidity:
                continue
            # Replace receivable/payable counterpart with mob/retention account
            if vals.get('account_id') and vals['account_id'] != liquidity.id:
                account = self.env['account.account'].browse(vals['account_id'])
                if account.account_type in ('asset_receivable', 'liability_payable'):
                    vals['account_id'] = counterpart.id
                elif vals['account_id'] == self.destination_account_id.id:
                    vals['account_id'] = counterpart.id
        return line_vals_list

    def _generate_move_vals(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        vals = super()._generate_move_vals(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
            line_ids=line_ids,
        )
        vals.update({
            'ages_sub_company_id': self.ages_sub_company_id.id,
            'ages_contract_id': self.ages_contract_id.id,
            'ages_project_id': self.ages_project_id.id,
            'ages_analytic_account_id': self.ages_analytic_account_id.id,
            'ages_running_bill_id': self.ages_running_bill_id.id,
            'ages_mobilization_advance_id': self.ages_mobilization_advance_id.id,
            'ages_retention_recovery_id': self.ages_retention_recovery_id.id,
        })
        return vals

    def _synchronize_to_moves(self, changed_fields):
        """Vendors Transfer / expense multi-line JEs break Odoo singleton counterpart sync."""
        if self.env.context.get('skip_account_move_synchronization'):
            return
        split = self.filtered(lambda pay: pay.is_vendors_transfer or pay.is_internal_transfer)
        # Expense (and similar) rebuilds create many counterpart lines; core does .id on them.
        multi = (self - split).filtered(
            lambda pay: pay.move_id and len(pay._seek_for_lines()[1]) > 1
        )
        super(AccountPayment, self - split - multi)._synchronize_to_moves(changed_fields)

    def _generate_journal_entry(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        split = self.filtered(lambda pay: pay.is_vendors_transfer or pay.is_internal_transfer)
        return super(AccountPayment, self - split)._generate_journal_entry(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
            line_ids=line_ids,
        )

    def action_post(self):
        internal_transfers = self.filtered(lambda p: p.is_internal_transfer)
        vendors_transfers = self.filtered(lambda p: p.is_vendors_transfer)
        normal_payments = self - internal_transfers - vendors_transfers

        vendors_transfers._ages_sync_vendors_transfer_move(strict=True)

        res = super(AccountPayment, normal_payments | vendors_transfers).action_post() if (normal_payments | vendors_transfers) else True

        for payment in internal_transfers:
            payment._post_internal_transfer_payments()

        return res

    def action_draft(self):
        """Reset payment and its JE without tax-sync rewriting WHT lines."""
        self.state = 'draft'
        self.move_id.with_context(skip_invoice_sync=True).button_draft()

    def _ages_validate_internal_transfer_details(self):
        self.ensure_one()
        lines = self.payment_detail_line_ids
        if not lines:
            raise UserError(_(
                'Add at least one Payment Detail line with Destination Journal and Amount.'
            ))
        for line in lines:
            if not line.destination_journal_id:
                raise UserError(_('Every Payment Detail line must have a Destination Journal.'))
            if line.destination_journal_id == self.journal_id:
                raise UserError(_(
                    'Destination Journal must be different from the source Journal (%s).'
                ) % self.journal_id.display_name)
            if not line.destination_journal_id.default_account_id:
                raise UserError(_(
                    'Default account is missing on destination journal %s.'
                ) % line.destination_journal_id.display_name)
            if line.ages_project_id and not line.ages_analytic_account_id:
                raise UserError(_(
                    "Project '%s' has no analytic account."
                ) % line.ages_project_id.display_name)
            if not line.amount or line.amount <= 0:
                raise UserError(_('Every Payment Detail line amount must be greater than zero.'))

        if not self.journal_id.default_account_id:
            raise UserError(_(
                'Default account is missing on source journal %s.'
            ) % self.journal_id.display_name)

    def _ages_internal_transfer_details_ready(self):
        self.ensure_one()
        lines = self.payment_detail_line_ids
        if not lines or not self.journal_id or not self.journal_id.default_account_id:
            return False
        return all(
            line.destination_journal_id
            and line.destination_journal_id != self.journal_id
            and line.destination_journal_id.default_account_id
            and line.amount > 0
            for line in lines
        )

    def _ages_internal_transfer_move_vals(self):
        """Build the internal-transfer journal entry (draft or posted)."""
        self.ensure_one()
        total_amount = sum(self.payment_detail_line_ids.mapped('amount'))
        source_journal = self.journal_id
        source_account = source_journal.default_account_id
        source_dist = self._ages_payment_liquidity_analytic_distribution()
        move_line_cmds = []
        memo = self.memo or self.description or self.name or _('Internal Transfer')

        if self.payment_type == 'outbound':
            for detail in self.payment_detail_line_ids:
                dest_journal = detail.destination_journal_id
                move_line_cmds.append(Command.create({
                    'name': detail.description or _('Transfer to %s') % dest_journal.display_name,
                    'account_id': dest_journal.default_account_id.id,
                    'debit': detail.amount,
                    'credit': 0.0,
                    'analytic_distribution': detail._ages_analytic_distribution(),
                }))
            move_line_cmds.append(Command.create({
                'name': memo,
                'account_id': source_account.id,
                'debit': 0.0,
                'credit': total_amount,
                'analytic_distribution': source_dist or False,
            }))
        else:
            move_line_cmds.append(Command.create({
                'name': memo,
                'account_id': source_account.id,
                'debit': total_amount,
                'credit': 0.0,
                'analytic_distribution': source_dist or False,
            }))
            for detail in self.payment_detail_line_ids:
                dest_journal = detail.destination_journal_id
                move_line_cmds.append(Command.create({
                    'name': detail.description or _('Transfer from %s') % dest_journal.display_name,
                    'account_id': dest_journal.default_account_id.id,
                    'debit': 0.0,
                    'credit': detail.amount,
                    'analytic_distribution': detail._ages_analytic_distribution(),
                }))

        line_projects = self.payment_detail_line_ids.mapped('ages_project_id')
        unique_project = line_projects[:1] if len(line_projects) == 1 else self.env['project.project']
        unique_analytic = unique_project.account_id if unique_project else False
        move_vals = {
            'move_type': 'entry',
            'journal_id': source_journal.id,
            'date': self.date,
            'ref': memo,
            'company_id': self.company_id.id,
            'origin_payment_id': self.id,
            'ages_sub_company_id': self.ages_sub_company_id.id if self.ages_sub_company_id else False,
            'ages_contract_id': self.ages_contract_id.id if self.ages_contract_id else False,
            'ages_project_id': unique_project.id if unique_project else False,
            'line_ids': move_line_cmds,
        }
        if 'ages_analytic_account_id' in self.env['account.move']._fields:
            move_vals['ages_analytic_account_id'] = unique_analytic.id if unique_analytic else False
        return move_vals, total_amount

    def _ages_sync_internal_transfer_draft_move(self):
        """Create or refresh the internal-transfer journal entry without posting."""
        self.ensure_one()
        if (
            not self.is_internal_transfer
            or self.state == 'canceled'
            or (self.move_id and self.move_id.state != 'draft')
            or not self._ages_internal_transfer_details_ready()
        ):
            return
        move_vals, total_amount = self._ages_internal_transfer_move_vals()
        commands = move_vals['line_ids']
        payment = self.with_context(ages_skip_journal_sequence=True)
        if payment.move_id:
            write_vals = {key: value for key, value in move_vals.items() if key != 'line_ids'}
            if payment.move_id.journal_id != payment.journal_id:
                write_vals['name'] = '/'
            write_vals['line_ids'] = [Command.clear()] + commands
            payment.move_id.with_context(skip_invoice_sync=True).write(write_vals)
            super(AccountPayment, payment).write({'amount': total_amount})
        else:
            move = self.env['account.move'].with_context(
                skip_invoice_sync=True,
                is_payment=True,
            ).create(move_vals)
            super(AccountPayment, payment).write({
                'move_id': move.id,
                'amount': total_amount,
            })

    def _post_internal_transfer_payments(self):
        """
        Post one JE for internal transfer from Payment Details:

        Send (outbound):
          - Debit each destination journal account (line analytic 100%)
          - Credit source journal account (optional 100% payment analytic)

        Receive (inbound):
          - Debit source journal account (optional 100% payment analytic)
          - Credit each destination journal account (line analytic 100%)
        """
        self.ensure_one()
        self._ages_validate_internal_transfer_details()
        self._ages_validate_payment_liquidity_analytic()

        move_vals, total_amount = self._ages_internal_transfer_move_vals()
        move_line_cmds = move_vals['line_ids']

        if self.move_id:
            move = self.move_id
            if move.state == 'posted':
                move.line_ids.remove_move_reconcile()
                move.with_context(skip_invoice_sync=True).button_draft()
            write_vals = {key: value for key, value in move_vals.items() if key != 'line_ids'}
            write_vals['line_ids'] = [Command.clear()] + move_line_cmds
            move.with_context(skip_invoice_sync=True).write(write_vals)
        else:
            move = self.env['account.move'].with_context(is_payment=True).create(move_vals)

        reserved_name = self.name if self._ages_has_journal_sequence_name() else False
        if reserved_name and (not move.name or move.name == '/'):
            move.with_context(skip_invoice_sync=True).write({'name': reserved_name})
        elif not move.name or move.name == '/':
            move.with_context(is_payment=True)._set_next_sequence()
        move.action_post()

        self.with_context(ages_skip_journal_sequence=True).write({
            'state': 'paid',
            'move_id': move.id,
            'amount': total_amount,
        })

    @api.onchange('payment_detail_line_ids', 'is_internal_transfer', 'is_vendors_transfer')
    def _onchange_payment_detail_line_ids(self):
        if self._ages_uses_payment_details() and self.payment_detail_line_ids:
            self.amount = sum(self.payment_detail_line_ids.mapped('amount'))

    @api.depends('move_id.name', 'state')
    def _compute_name(self):
        """Use the journal-entry number (PCSH-HO/…), never PAY00004."""
        for payment in self:
            move_name = payment.move_id.name if payment.move_id else False
            if (
                move_name
                and move_name != '/'
                and not payment._ages_is_pay_fallback_name(move_name)
            ):
                payment.name = move_name
            elif (
                payment.name
                and payment.name != '/'
                and not payment._ages_is_pay_fallback_name(payment.name)
            ):
                payment.name = payment.name
            else:
                payment.name = False

    @api.depends('name', 'move_id.name')
    def _compute_display_name(self):
        for payment in self:
            payment.display_name = payment.name or _('Draft Payment')

    def _ages_is_pay_fallback_name(self, name=None):
        value = self.name if name is None else name
        if not value or value == '/':
            return False
        return bool(re.match(r'^PAY\d+$', str(value).upper()))

    def _ages_has_journal_sequence_name(self):
        self.ensure_one()
        name = self.name or ''
        return bool(name) and name != '/' and not self._ages_is_pay_fallback_name(name)

    def _ages_create_sequence_stub_move(self):
        self.ensure_one()
        vals = {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'origin_payment_id': self.id,
            'ref': self.memo or False,
            'ages_sub_company_id': self.ages_sub_company_id.id if self.ages_sub_company_id else False,
            'ages_contract_id': self.ages_contract_id.id if self.ages_contract_id else False,
            'ages_project_id': self.ages_project_id.id if self.ages_project_id else False,
        }
        if 'ages_analytic_account_id' in self.env['account.move']._fields:
            vals['ages_analytic_account_id'] = (
                self.ages_analytic_account_id.id if self.ages_analytic_account_id else False
            )
        return self.env['account.move'].with_context(
            skip_invoice_sync=True,
            is_payment=True,
        ).create(vals)

    def _ages_attach_sequence_stub_move(self):
        self.ensure_one()
        if self.move_id or not self.journal_id:
            return
        move = self._ages_create_sequence_stub_move()
        super(AccountPayment, self.with_context(ages_skip_journal_sequence=True)).write({
            'move_id': move.id,
        })

    def _ages_existing_payment_moves(self):
        """Moves already created for this payment, including orphans from a failed link."""
        self.ensure_one()
        moves = self.move_id
        if self.id:
            moves |= self.env['account.move'].search([('origin_payment_id', '=', self.id)])
        return moves

    def _ages_ensure_standard_draft_move(self):
        self.ensure_one()
        if not self.journal_id:
            return
        if not self.move_id:
            existing = self._ages_existing_payment_moves()[:1]
            if existing:
                super(AccountPayment, self.with_context(ages_skip_journal_sequence=True)).write({
                    'move_id': existing.id,
                })
        if self.move_id:
            if (
                self.move_id.state != 'draft'
                or self.move_id.line_ids
                or not self.outstanding_account_id
                or not self.destination_account_id
            ):
                return
            move_vals = self._generate_move_vals()
            self.move_id.with_context(skip_invoice_sync=True).write({
                'date': self.date,
                'partner_id': self.partner_id.id,
                'journal_id': self.journal_id.id,
                'line_ids': [Command.clear()] + list(move_vals.get('line_ids') or []),
            })
            return
        if not self.outstanding_account_id or not self.destination_account_id:
            self._ages_attach_sequence_stub_move()
            return
        move_vals = self._generate_move_vals()
        move = self.env['account.move'].with_context(
            skip_invoice_sync=True,
            is_payment=True,
        ).create(move_vals)
        super(AccountPayment, self.with_context(ages_skip_journal_sequence=True)).write({
            'move_id': move.id,
        })

    def _ages_name_draft_move(self):
        self.ensure_one()
        move = self.move_id
        if not move or move.state != 'draft' or not move.journal_id or not move.date:
            return
        if move.journal_id != self.journal_id:
            move.with_context(skip_invoice_sync=True).write({
                'journal_id': self.journal_id.id,
                'name': '/',
            })
        if (
            move.name
            and move.name != '/'
            and not self._ages_is_pay_fallback_name(move.name)
            and move._sequence_matches_date()
        ):
            return
        if move.name and move.name != '/':
            move.with_context(skip_invoice_sync=True).write({'name': '/'})
        move.with_context(is_payment=True, skip_invoice_sync=True)._set_next_sequence()
        if self._fields['name'].store and self._fields['name'].compute:
            self.env.add_to_compute(self._fields['name'], self)

    def _ages_assign_journal_sequence(self):
        """Reserve the journal payment number on Save (draft JE, not PAY…)."""
        if self.env.context.get('ages_skip_journal_sequence'):
            return
        for payment in self.filtered(lambda pay: pay.id and pay.state == 'draft' and pay.journal_id):
            payment = payment.with_context(ages_skip_journal_sequence=True)
            if payment.is_internal_transfer:
                if payment._ages_internal_transfer_details_ready():
                    payment._ages_sync_internal_transfer_draft_move()
                elif not payment.move_id:
                    payment._ages_attach_sequence_stub_move()
            elif payment.is_vendors_transfer:
                if payment._ages_vendors_transfer_details_ready():
                    payment._ages_sync_vendors_transfer_move(strict=False)
                elif not payment.move_id:
                    payment._ages_attach_sequence_stub_move()
            else:
                payment._ages_ensure_standard_draft_move()
            payment._ages_name_draft_move()

    def _ages_liquidity_account(self):
        self.ensure_one()
        return self.outstanding_account_id or self.journal_id.default_account_id

    def _ages_vendors_transfer_details_ready(self):
        self.ensure_one()
        lines = self.payment_detail_line_ids
        if not lines:
            return False
        return all(line.partner_id and line.amount > 0 for line in lines)

    def _ages_validate_vendors_transfer_details(self):
        self.ensure_one()
        if self.payment_type != 'outbound':
            raise UserError(_('Vendors Transfer is only available for Send payments.'))
        lines = self.payment_detail_line_ids
        if not lines:
            raise UserError(_('Add at least one Payment Detail line with Vendor and Amount.'))
        self._ages_validate_payment_liquidity_analytic()
        if not self._ages_liquidity_account():
            raise UserError(_(
                'Set an outstanding payments account on the payment method, or a default account on journal %s.'
            ) % self.journal_id.display_name)
        for line in lines:
            if not line.partner_id:
                raise UserError(_('Every Payment Detail line must have a Vendor.'))
            if not line.amount or line.amount <= 0:
                raise UserError(_('Every Payment Detail line amount must be greater than zero.'))
            payable = line.partner_id.with_company(self.company_id).property_account_payable_id
            if not payable:
                raise UserError(_(
                    "Vendor '%s' has no payable account."
                ) % line.partner_id.display_name)
            if line.ages_project_id and not (
                line.analytic_distribution or line.ages_analytic_account_id
            ):
                raise UserError(_(
                    "Project '%s' has no analytic account."
                ) % line.ages_project_id.display_name)

    def _ages_vendors_transfer_move_line_commands(self):
        """Credit the cash/bank journal once; debit each vendor payable separately."""
        self.ensure_one()
        total_amount = sum(self.payment_detail_line_ids.mapped('amount'))
        liquidity = self._ages_liquidity_account()
        source_dist = self._ages_payment_liquidity_analytic_distribution()
        memo = self.memo or self.description or self.name or _('Vendors Transfer')
        commands = []
        for detail in self.payment_detail_line_ids:
            vendor = detail.partner_id
            payable = vendor.with_company(self.company_id).property_account_payable_id
            commands.append(Command.create({
                'name': detail.description or _('Payment to %s') % vendor.display_name,
                'account_id': payable.id,
                'partner_id': vendor.id,
                'debit': detail.amount,
                'credit': 0.0,
                'analytic_distribution': detail._ages_analytic_distribution(),
            }))
        commands.append(Command.create({
            'name': memo,
            'account_id': liquidity.id,
            'debit': 0.0,
            'credit': total_amount,
            'analytic_distribution': source_dist or False,
        }))
        return commands, total_amount

    def _ages_sync_vendors_transfer_move(self, strict=False):
        """Create or refresh the multi-vendor journal entry (draft on Save, posted on Confirm)."""
        if self.env.context.get('ages_skip_vendors_transfer_sync'):
            return
        payments = self.with_context(ages_skip_vendors_transfer_sync=True)
        for payment in payments:
            if not payment.is_vendors_transfer or payment.state == 'canceled':
                continue
            if payment.move_id and payment.move_id.state != 'draft':
                continue
            if strict:
                payment._ages_validate_vendors_transfer_details()
            elif not payment._ages_vendors_transfer_details_ready():
                continue
            if not payment._ages_liquidity_account() or not payment.journal_id:
                continue
            commands, total_amount = payment._ages_vendors_transfer_move_line_commands()
            line_projects = payment.payment_detail_line_ids.mapped('ages_project_id')
            unique_project = line_projects[:1] if len(line_projects) == 1 else self.env['project.project']
            unique_analytic = unique_project.account_id if unique_project else False
            memo = payment.memo or payment.description or payment.name or _('Vendors Transfer')
            move_vals = {
                'move_type': 'entry',
                'journal_id': payment.journal_id.id,
                'date': payment.date,
                'ref': memo,
                'company_id': payment.company_id.id,
                'ages_sub_company_id': payment.ages_sub_company_id.id if payment.ages_sub_company_id else False,
                'ages_contract_id': payment.ages_contract_id.id if payment.ages_contract_id else False,
                'ages_project_id': unique_project.id if unique_project else False,
                'origin_payment_id': payment.id,
                'line_ids': commands,
            }
            if 'ages_analytic_account_id' in self.env['account.move']._fields:
                move_vals['ages_analytic_account_id'] = unique_analytic.id if unique_analytic else False
            if payment.move_id:
                write_vals = {
                    'date': payment.date,
                    'ref': memo,
                    'journal_id': payment.journal_id.id,
                    'ages_sub_company_id': move_vals['ages_sub_company_id'],
                    'ages_contract_id': move_vals['ages_contract_id'],
                    'ages_project_id': move_vals['ages_project_id'],
                    'line_ids': [Command.clear()] + commands,
                }
                if payment.move_id.journal_id != payment.journal_id:
                    write_vals['name'] = '/'
                payment.move_id.with_context(skip_invoice_sync=True).write(write_vals)
            else:
                move = self.env['account.move'].with_context(
                    skip_invoice_sync=True,
                    is_payment=True,
                ).create(move_vals)
                super(AccountPayment, payment).write({
                    'move_id': move.id,
                    'amount': total_amount,
                })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ages_fill_sub_company_from_project_vals(vals)
        payments = super().create(vals_list)
        payments._ages_sync_detail_amount()
        payments._ages_assign_journal_sequence()
        return payments

    def write(self, vals):
        if vals.get('ages_project_id') and 'ages_sub_company_id' not in vals:
            vals = dict(vals)
            self._ages_fill_sub_company_from_project_vals(vals)
        skip = self.env.context.get('ages_skip_journal_sequence')
        posting = vals.get('state') in ('in_process', 'paid')
        # Odoo attach/post already creates the JE. Reserving another number here
        # left a draft leftover (PJSBNK…/00037) plus the posted payment (00038).
        attaching_move = bool(vals.get('move_id'))
        if not skip and posting and not attaching_move:
            self.filtered(lambda pay: not pay.move_id)._ages_assign_journal_sequence()
        res = super().write(vals)
        if skip:
            return res
        self._ages_sync_detail_amount()
        if not posting and not attaching_move:
            self._ages_assign_journal_sequence()
        return res

    @api.model
    def _ages_fill_sub_company_from_project_vals(self, vals):
        if vals.get('ages_sub_company_id') or not vals.get('ages_project_id'):
            return
        project = self.env['project.project'].browse(vals['ages_project_id'])
        sub_company = self._ages_sub_company_from_project(project)
        if sub_company:
            vals['ages_sub_company_id'] = sub_company.id


class AccountPaymentDetailLine(models.Model):
    _name = 'account.payment.detail.line'
    _inherit = ['analytic.mixin']
    _description = 'Payment Detail Line'

    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Payment',
        ondelete='cascade',
        required=True,
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        domain="[('parent_id', '=', False)]",
        check_company=True,
    )
    destination_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Destination Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id), ('id', '!=', parent_journal_id)]",
        check_company=True,
    )
    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        check_company=True,
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        compute='_compute_ages_analytic_account_id',
        store=True,
        readonly=True,
    )
    description = fields.Char(
        string='Description',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        default=0.0,
    )
    currency_id = fields.Many2one(
        related='payment_id.currency_id',
        string='Currency',
        readonly=True,
    )
    company_id = fields.Many2one(
        related='payment_id.company_id',
        string='Company',
        readonly=True,
    )
    parent_journal_id = fields.Many2one(
        related='payment_id.journal_id',
        string='Source Journal',
        readonly=True,
    )

    @api.depends('ages_project_id', 'ages_project_id.account_id')
    def _compute_ages_analytic_account_id(self):
        for line in self:
            line.ages_analytic_account_id = (
                line.ages_project_id.account_id if line.ages_project_id else False
            )

    @api.depends('ages_project_id', 'ages_project_id.account_id')
    def _compute_analytic_distribution(self):
        for line in self:
            if line.analytic_distribution:
                line.analytic_distribution = line.analytic_distribution
            elif line.ages_project_id and line.ages_project_id.account_id:
                line.analytic_distribution = {str(line.ages_project_id.account_id.id): 100.0}
            else:
                line.analytic_distribution = False

    @api.onchange('ages_project_id')
    def _onchange_ages_project_id(self):
        if self.ages_project_id and self.ages_project_id.account_id:
            self.analytic_distribution = {str(self.ages_project_id.account_id.id): 100.0}
            payment = self.payment_id
            if payment:
                sub_company = payment._ages_sub_company_from_project(self.ages_project_id)
                if sub_company:
                    payment.ages_sub_company_id = sub_company
        elif not self.ages_project_id:
            self.analytic_distribution = False

    def _ages_analytic_distribution(self):
        self.ensure_one()
        if self.analytic_distribution:
            return self.analytic_distribution
        if not self.ages_analytic_account_id:
            return False
        return {str(self.ages_analytic_account_id.id): 100.0}

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        payments = lines.mapped('payment_id')
        payments._ages_sync_detail_amount()
        payments._ages_assign_journal_sequence()
        return lines

    def write(self, vals):
        res = super().write(vals)
        payments = self.mapped('payment_id')
        payments._ages_sync_detail_amount()
        payments._ages_assign_journal_sequence()
        return res

    def unlink(self):
        payments = self.mapped('payment_id')
        res = super().unlink()
        payments._ages_sync_detail_amount()
        payments._ages_assign_journal_sequence()
        return res

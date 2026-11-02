# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgesMobilizationAdvance(models.Model):
    _name = 'ages.mobilization.advance'
    _inherit = ['ages.mobilization.advance', 'mail.thread', 'mail.activity.mixin']
    _description = 'Mobilization Received'
    _order = 'id desc'

    name = fields.Char(
        string='Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('state', '=', 'running'), ('partner_id', '=', partner_id)]",
    )
    project_wise_contract = fields.Char(
        related='contract_id.project_wise_name',
        string='Project-Wise Contract',
        readonly=True,
    )
    contract_description = fields.Text(
        related='contract_id.contract_description',
        string='Contract Description',
        readonly=True,
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        required=True,
        tracking=True,
        domain="[('partner_id', '=', partner_id)]",
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        compute='_compute_analytic_account_id',
        store=True,
        readonly=True,
    )
    sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        compute='_compute_sub_company_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    mobilization_amount = fields.Monetary(
        string='Mobilization Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
        help='Auto-fetched from Contract Total Mobilization Amount; changeable if needed.',
    )
    wht_on_mobilization = fields.Boolean(
        related='contract_id.wht_on_mobilization',
        string='WHT on Mobilization',
    )
    wth_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='WHT (%)',
        compute='_compute_wth_tax_id',
        store=True,
        readonly=False,
        domain="[('is_withholding_tax_on_payment', '=', True), ('active', '=', True)]",
        check_company=True,
    )
    wth_amount = fields.Monetary(
        string='WHT Amount',
        compute='_compute_wth_amount',
        store=True,
        currency_field='currency_id',
    )
    running_bill_id = fields.Many2one(
        comodel_name='ages.running.bill',
        string='Running Bill',
        domain="[('contract_id', '=', contract_id)]",
        copy=False,
    )

    # ---- Invoice link ----
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        copy=False,
        readonly=True,
    )
    invoice_state = fields.Selection(
        related='invoice_id.state',
        string='Invoice Move Status',
        store=True,
    )
    invoice_payment_state = fields.Selection(
        related='invoice_id.payment_state',
        string='Invoice Status',
        store=True,
    )
    contract_count = fields.Integer(
        string='Contract Count',
        compute='_compute_contract_count',
    )

    # -------------------------------------------------------------------------
    # Computes / onchange
    # -------------------------------------------------------------------------
    @api.depends('contract_id')
    def _compute_contract_count(self):
        for rec in self:
            rec.contract_count = 1 if rec.contract_id else 0

    @api.depends('project_id', 'project_id.account_id')
    def _compute_analytic_account_id(self):
        for rec in self:
            rec.analytic_account_id = rec.project_id.account_id

    @api.depends('contract_id', 'contract_id.sub_company_id', 'project_id', 'project_id.ages_contract_id')
    def _compute_sub_company_id(self):
        for rec in self:
            if rec.contract_id:
                rec.sub_company_id = rec.contract_id.sub_company_id
            elif rec.project_id and rec.project_id.ages_contract_id:
                rec.sub_company_id = rec.project_id.ages_contract_id.sub_company_id
            else:
                rec.sub_company_id = False

    @api.depends('contract_id', 'contract_id.wth_tax_id', 'contract_id.wht_on_mobilization')
    def _compute_wth_tax_id(self):
        for rec in self:
            if rec.contract_id.wht_on_mobilization:
                rec.wth_tax_id = rec.contract_id.wth_tax_id
            else:
                rec.wth_tax_id = False

    @api.depends('wth_tax_id', 'wth_tax_id.amount', 'wth_tax_id.amount_type', 'mobilization_amount')
    def _compute_wth_amount(self):
        for rec in self:
            tax = rec.wth_tax_id
            base = rec.mobilization_amount or 0.0
            if not tax or not rec.wht_on_mobilization:
                rec.wth_amount = 0.0
            elif tax.amount_type == 'fixed':
                rec.wth_amount = tax.amount or 0.0
            else:
                rec.wth_amount = base * (tax.amount or 0.0) / 100.0

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if not self.contract_id:
            return
        contract = self.contract_id
        self.partner_id = contract.partner_id
        self.project_id = contract.project_id
        self.company_id = contract.company_id
        self.mobilization_amount = contract.total_mobilization_amount or 0.0
        self.wth_tax_id = contract.wth_tax_id if contract.wht_on_mobilization else False
        if self.running_bill_id and self.running_bill_id.contract_id != contract:
            self.running_bill_id = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.contract_id and self.contract_id.partner_id != self.partner_id:
            self.contract_id = False
            self.project_id = False
            self.running_bill_id = False
        if not self.partner_id:
            return
        contracts = self.env['ages.contract'].search([
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'running'),
            ('company_id', '=', self.company_id.id if self.company_id else self.env.company.id),
        ], order='id desc')
        if len(contracts) == 1:
            self.contract_id = contracts
            self._onchange_contract_id()
        elif self.contract_id and self.contract_id not in contracts:
            self.contract_id = False
            self.project_id = False
            self.running_bill_id = False

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) in (_('New'), 'New', False):
                vals['name'] = sequence.next_by_code('ages.mobilization.advance') or _('New')
            if vals.get('contract_id') and not vals.get('project_id'):
                contract = self.env['ages.contract'].browse(vals['contract_id'])
                if contract.project_id:
                    vals['project_id'] = contract.project_id.id
        records = super().create(vals_list)
        for rec in records.filtered('contract_id'):
            if not rec.project_id and rec.contract_id.project_id:
                rec.project_id = rec.contract_id.project_id.id
            if not rec.contract_id.mobilization_advance_id:
                rec.contract_id.with_context(ages_skip_lock=True).write({
                    'mobilization_advance_id': rec.id,
                })
        return records

    def unlink(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_(
                    'You cannot delete a Confirmed Mobilization Received (%s). '
                    'Reset it first if you need to remove it.'
                ) % rec.display_name)
        contracts = self.mapped('contract_id').filtered(
            lambda c: c.mobilization_advance_id and c.mobilization_advance_id in self
        )
        res = super().unlink()
        if contracts:
            contracts.with_context(ages_skip_lock=True).write({'mobilization_advance_id': False})
        return res

    @api.model
    def create_from_contract(self, contract):
        """Factory used by Contract → Mobilization Receiving."""
        contract.ensure_one()
        return self.create({
            'partner_id': contract.partner_id.id,
            'contract_id': contract.id,
            'project_id': contract.project_id.id,
            'company_id': contract.company_id.id,
            'date': fields.Date.context_today(self),
            'mobilization_amount': contract.total_mobilization_amount or 0.0,
            'wth_tax_id': contract.wth_tax_id.id if contract.wht_on_mobilization else False,
        })

    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft records can be confirmed.'))
            rec._check_confirm_ready()
            rec.write({'state': 'confirmed'})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft records can be cancelled.'))
            posted_payments = False
            if 'payment_ids' in rec._fields:
                posted_payments = rec.payment_ids.filtered(
                    lambda p: p.state not in ('draft', 'canceled', 'rejected', 'cancel')
                )
            if posted_payments:
                raise UserError(_('You cannot cancel when payments are already posted.'))
            if rec.invoice_id and rec.invoice_id.state == 'posted':
                raise UserError(_('You cannot cancel when the linked invoice is Posted.'))
            rec.state = 'cancelled'
        return True

    def action_reset(self):
        """Reset Mobilization Received to Draft (legacy invoice cleanup if any)."""
        for rec in self:
            if rec.state not in ('confirmed', 'cancelled'):
                raise UserError(_('Only Confirmed or Cancelled records can be reset.'))
            invoice = rec.invoice_id
            if invoice:
                if invoice.payment_state in ('paid', 'partial', 'in_payment'):
                    raise UserError(_(
                        'You cannot reset %s because linked invoice %s has payments.'
                    ) % (rec.display_name, invoice.display_name))
                if invoice.state == 'posted':
                    invoice.button_draft()
                if invoice.state == 'draft':
                    invoice.button_cancel()
                if invoice.state == 'cancel':
                    invoice.with_context(force_delete=True).unlink()
                else:
                    raise UserError(_(
                        'Unable to reset linked invoice %s. Please reset/cancel it manually.'
                    ) % invoice.display_name)
            rec.write({
                'state': 'draft',
                'invoice_id': False,
            })
        return True

    def action_view_invoice(self):
        """Legacy helper for old invoice-linked records."""
        self.ensure_one()
        if not self.invoice_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_contract(self):
        self.ensure_one()
        if not self.contract_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract'),
            'res_model': 'ages.contract',
            'res_id': self.contract_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _check_confirm_ready(self):
        self.ensure_one()
        if not self.partner_id or not self.contract_id or not self.project_id:
            raise UserError(_('Client, Contract and Project are required.'))
        if not self.date:
            raise UserError(_('Date is required.'))
        if not self.mobilization_amount:
            raise UserError(_('Mobilization Amount must be greater than zero.'))
        if not self.company_id.ages_mobilization_account_id:
            raise UserError(_(
                'Please configure Mobilization Account in '
                'Project → Configuration → Settings → Default Accounts.'
            ))

    @api.constrains('mobilization_amount', 'contract_id')
    def _check_mobilization_amount_limit(self):
        for rec in self:
            if rec.contract_id and rec.mobilization_amount:
                max_amount = rec.contract_id.total_mobilization_amount or 0.0
                if rec.mobilization_amount > max_amount:
                    raise UserError(_(
                        "Mobilization Amount (%s) cannot exceed the Contract Mobilization Amount (%s)."
                    ) % (rec.mobilization_amount, max_amount))

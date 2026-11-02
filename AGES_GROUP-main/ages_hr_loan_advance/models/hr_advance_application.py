# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class HrAdvanceApplication(models.Model):
    _name = 'hr.advance.application'
    _description = 'Advance Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, tracking=True,
        check_company=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    date = fields.Date(
        string='Advance Date', required=True, tracking=True,
        default=fields.Date.context_today)
    recovery_date = fields.Date(
        string='Recovery From',
        help='First payslip period on/after this date may deduct the advance. '
             'Defaults to the advance date.',
        default=fields.Date.context_today)
    amount = fields.Monetary(required=True, tracking=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        tracking=True)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank'),
    ], string='Payment Method', required=True, default='cash', tracking=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', check_company=True,
        tracking=True)
    receivable_account_id = fields.Many2one(
        'account.account', string='Advance Account',
        check_company=True, tracking=True)
    payment_account_id = fields.Many2one(
        'account.account', string='Cash/Bank Account',
        check_company=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('confirmed', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    note = fields.Text()

    amount_deducted = fields.Monetary(
        string='Deducted', currency_field='currency_id',
        compute='_compute_deduction_amounts', store=True)
    amount_residual = fields.Monetary(
        string='Residual', currency_field='currency_id',
        compute='_compute_deduction_amounts', store=True)
    deduction_state = fields.Selection([
        ('pending', 'Not Deducted'),
        ('partial', 'Partially Deducted'),
        ('deducted', 'Deducted'),
        ('skipped', 'Skipped'),
    ], string='Deduction Status', default='pending', copy=False, tracking=True)
    skip_next_payslip = fields.Boolean(
        string='Skip Next Payslip',
        help='If set, this advance will not be auto-added on the next payslip compute. '
             'Clear it to resume automatic recovery.')
    payslip_input_ids = fields.One2many(
        'hr.payslip.input', 'advance_id', string='Payslip Inputs')
    payslip_ids = fields.Many2many(
        'hr.payslip', string='Payslips', compute='_compute_payslip_ids')
    payslip_count = fields.Integer(compute='_compute_payslip_ids')

    @api.depends('payslip_input_ids', 'payslip_input_ids.amount', 'payslip_input_ids.payslip_id.state', 'amount')
    def _compute_deduction_amounts(self):
        for rec in self:
            done_inputs = rec.payslip_input_ids.filtered(
                lambda l: l.payslip_id.state in ('done', 'paid'))
            deducted = sum(done_inputs.mapped('amount'))
            rec.amount_deducted = deducted
            rec.amount_residual = max(rec.amount - deducted, 0.0)

    @api.depends('payslip_input_ids.payslip_id')
    def _compute_payslip_ids(self):
        for rec in self:
            slips = rec.payslip_input_ids.mapped('payslip_id')
            rec.payslip_ids = slips
            rec.payslip_count = len(slips)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        company = self.company_id
        if company:
            self.journal_id = company.advance_journal_id
            self.receivable_account_id = company.advance_receivable_account_id
            self.payment_account_id = company.advance_payment_account_id

    @api.onchange('payment_method', 'company_id')
    def _onchange_payment_method(self):
        if self.company_id and self.company_id.advance_payment_account_id:
            self.payment_account_id = self.company_id.advance_payment_account_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id)
            if not vals.get('journal_id') and company.advance_journal_id:
                vals['journal_id'] = company.advance_journal_id.id
            if not vals.get('receivable_account_id') and company.advance_receivable_account_id:
                vals['receivable_account_id'] = company.advance_receivable_account_id.id
            if not vals.get('payment_account_id') and company.advance_payment_account_id:
                vals['payment_account_id'] = company.advance_payment_account_id.id
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.advance.application') or _('New')
            if not vals.get('recovery_date') and vals.get('date'):
                vals['recovery_date'] = vals['date']
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'confirmed' for rec in self):
            raise UserError(_('You cannot delete a confirmed advance application.'))
        return super().unlink()

    def action_submit(self):
        self._check_required_accounts()
        self.write({'state': 'to_approve'})

    def action_approve(self):
        self.filtered(lambda r: r.state == 'to_approve').write({'state': 'approved'})

    def action_refuse(self):
        self.filtered(lambda r: r.state == 'to_approve').write({'state': 'draft'})

    def action_reset_draft(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('Confirmed advances cannot be reset to draft.'))
        self.write({'state': 'draft'})

    def action_cancel(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('Confirmed advances cannot be cancelled. Reverse the journal entry in Accounting if needed.'))
        self.write({'state': 'cancel'})

    def action_confirm(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('Only approved advances can be confirmed.'))
            rec._check_required_accounts()
            if float_compare(rec.amount, 0.0, precision_rounding=rec.currency_id.rounding) <= 0:
                raise ValidationError(_('Advance amount must be greater than zero.'))
            move = rec._create_disbursement_move()
            rec.write({
                'move_id': move.id,
                'state': 'confirmed',
                'deduction_state': 'pending',
            })

    def _check_required_accounts(self):
        for rec in self:
            missing = []
            if not rec.journal_id:
                missing.append(_('Journal'))
            if not rec.receivable_account_id:
                missing.append(_('Advance Account'))
            if not rec.payment_account_id:
                missing.append(_('Cash/Bank Account'))
            if missing:
                raise UserError(_(
                    'Please configure %(fields)s on the advance (or in Payroll Settings).',
                    fields=', '.join(missing),
                ))

    def _create_disbursement_move(self):
        self.ensure_one()
        move_vals = {
            'ref': self.name,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'narration': _('Employee Advance: %s — %s') % (self.employee_id.name, self.name),
            'line_ids': [
                (0, 0, {
                    'name': _('Advance receivable — %s') % self.employee_id.name,
                    'account_id': self.receivable_account_id.id,
                    'partner_id': self.employee_id.work_contact_id.id or False,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Advance payment — %s (%s)') % (
                        self.employee_id.name, self.payment_method),
                    'account_id': self.payment_account_id.id,
                    'partner_id': self.employee_id.work_contact_id.id or False,
                    'debit': 0.0,
                    'credit': self.amount,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        return move

    def _get_pending_amount_for_payslip(self, payslip):
        self.ensure_one()
        if self.state != 'confirmed' or self.skip_next_payslip:
            return 0.0
        if self.deduction_state == 'deducted':
            return 0.0
        recovery = self.recovery_date or self.date
        if recovery and recovery > payslip.date_to:
            return 0.0
        if float_is_zero(self.amount_residual, precision_rounding=self.currency_id.rounding):
            return 0.0
        return self.amount_residual

    def action_mark_skipped(self):
        self.write({'skip_next_payslip': True, 'deduction_state': 'skipped'})

    def action_resume_deduction(self):
        for rec in self:
            vals = {'skip_next_payslip': False}
            if rec.deduction_state == 'skipped':
                if float_is_zero(rec.amount_residual, precision_rounding=rec.currency_id.rounding):
                    vals['deduction_state'] = 'deducted'
                elif float_compare(rec.amount_deducted, 0.0, precision_rounding=rec.currency_id.rounding) > 0:
                    vals['deduction_state'] = 'partial'
                else:
                    vals['deduction_state'] = 'pending'
            rec.write(vals)

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslips'),
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.payslip_ids.ids)],
        }

    def action_open_move(self):
        self.ensure_one()
        if not self.move_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    def _update_deduction_state_from_amounts(self):
        for rec in self:
            rounding = rec.currency_id.rounding
            if float_is_zero(rec.amount_residual, precision_rounding=rounding):
                rec.deduction_state = 'deducted'
                rec.skip_next_payslip = False
            elif float_compare(rec.amount_deducted, 0.0, precision_rounding=rounding) > 0:
                rec.deduction_state = 'partial'
            elif rec.skip_next_payslip:
                rec.deduction_state = 'skipped'
            else:
                rec.deduction_state = 'pending'

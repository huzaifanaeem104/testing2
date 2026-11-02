# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round


class HrLoanApplication(models.Model):
    _name = 'hr.loan.application'
    _description = 'Loan Application'
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
        string='Loan Date', required=True, tracking=True,
        default=fields.Date.context_today)
    amount = fields.Monetary(required=True, tracking=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
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
        'account.account', string='Loan Account',
        check_company=True, tracking=True)
    payment_account_id = fields.Many2one(
        'account.account', string='Cash/Bank Account',
        check_company=True, tracking=True)
    installment_count = fields.Integer(
        string='Number of Installments', required=True, default=12, tracking=True)
    first_installment_date = fields.Date(
        string='First Installment Date', required=True,
        default=fields.Date.context_today)
    installment_amount = fields.Monetary(
        string='Installment Amount', currency_field='currency_id',
        compute='_compute_installment_amount', store=True)
    installment_ids = fields.One2many(
        'hr.loan.installment', 'loan_id', string='Installments', copy=False)
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
        currency_field='currency_id', compute='_compute_deduction_totals', store=True)
    amount_residual = fields.Monetary(
        currency_field='currency_id', compute='_compute_deduction_totals', store=True)
    deduction_state = fields.Selection([
        ('pending', 'Not Deducted'),
        ('partial', 'Partially Deducted'),
        ('deducted', 'Deducted'),
        ('skipped', 'Skipped'),
    ], string='Deduction Status', default='pending', copy=False, tracking=True)
    installment_count_done = fields.Integer(compute='_compute_deduction_totals', store=True)

    @api.depends('amount', 'installment_count')
    def _compute_installment_amount(self):
        for rec in self:
            if rec.installment_count and rec.installment_count > 0:
                rec.installment_amount = float_round(
                    rec.amount / rec.installment_count,
                    precision_rounding=rec.currency_id.rounding or 0.01)
            else:
                rec.installment_amount = 0.0

    @api.depends(
        'installment_ids.amount_deducted', 'installment_ids.amount_residual',
        'installment_ids.deduction_state', 'amount')
    def _compute_deduction_totals(self):
        for rec in self:
            deducted = sum(rec.installment_ids.mapped('amount_deducted'))
            rec.amount_deducted = deducted
            rec.amount_residual = max(rec.amount - deducted, 0.0)
            rec.installment_count_done = len(
                rec.installment_ids.filtered(lambda i: i.deduction_state == 'deducted'))

    @api.onchange('company_id')
    def _onchange_company_id(self):
        company = self.company_id
        if company:
            self.journal_id = company.loan_journal_id
            self.receivable_account_id = company.loan_receivable_account_id
            self.payment_account_id = company.loan_payment_account_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id)
            if not vals.get('journal_id') and company.loan_journal_id:
                vals['journal_id'] = company.loan_journal_id.id
            if not vals.get('receivable_account_id') and company.loan_receivable_account_id:
                vals['receivable_account_id'] = company.loan_receivable_account_id.id
            if not vals.get('payment_account_id') and company.loan_payment_account_id:
                vals['payment_account_id'] = company.loan_payment_account_id.id
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.loan.application') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'confirmed' for rec in self):
            raise UserError(_('You cannot delete a confirmed loan application.'))
        return super().unlink()

    def action_submit(self):
        self._check_required_accounts()
        self._check_installment_params()
        self.write({'state': 'to_approve'})

    def action_approve(self):
        self.filtered(lambda r: r.state == 'to_approve').write({'state': 'approved'})

    def action_refuse(self):
        self.filtered(lambda r: r.state == 'to_approve').write({'state': 'draft'})

    def action_reset_draft(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('Confirmed loans cannot be reset to draft.'))
        self.write({'state': 'draft'})

    def action_cancel(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('Confirmed loans cannot be cancelled. Reverse the journal entry in Accounting if needed.'))
        self.write({'state': 'cancel'})

    def action_confirm(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('Only approved loans can be confirmed.'))
            rec._check_required_accounts()
            rec._check_installment_params()
            move = rec._create_disbursement_move()
            rec._generate_installments()
            rec.write({
                'move_id': move.id,
                'state': 'confirmed',
                'deduction_state': 'pending',
            })

    def _check_installment_params(self):
        for rec in self:
            if rec.installment_count <= 0:
                raise ValidationError(_('Number of installments must be greater than zero.'))
            if float_compare(rec.amount, 0.0, precision_rounding=rec.currency_id.rounding) <= 0:
                raise ValidationError(_('Loan amount must be greater than zero.'))
            if not rec.first_installment_date:
                raise ValidationError(_('First installment date is required.'))

    def _check_required_accounts(self):
        for rec in self:
            missing = []
            if not rec.journal_id:
                missing.append(_('Journal'))
            if not rec.receivable_account_id:
                missing.append(_('Loan Account'))
            if not rec.payment_account_id:
                missing.append(_('Cash/Bank Account'))
            if missing:
                raise UserError(_(
                    'Please configure %(fields)s on the loan (or in Payroll Settings).',
                    fields=', '.join(missing),
                ))

    def _create_disbursement_move(self):
        self.ensure_one()
        move_vals = {
            'ref': self.name,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'narration': _('Employee Loan: %s — %s') % (self.employee_id.name, self.name),
            'line_ids': [
                (0, 0, {
                    'name': _('Loan receivable — %s') % self.employee_id.name,
                    'account_id': self.receivable_account_id.id,
                    'partner_id': self.employee_id.work_contact_id.id or False,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Loan payment — %s (%s)') % (
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

    def _generate_installments(self):
        self.ensure_one()
        self.installment_ids.unlink()
        rounding = self.currency_id.rounding or 0.01
        base = float_round(self.amount / self.installment_count, precision_rounding=rounding)
        lines = []
        allocated = 0.0
        for index in range(1, self.installment_count + 1):
            due = self.first_installment_date + relativedelta(months=index - 1)
            if index == self.installment_count:
                amount = float_round(self.amount - allocated, precision_rounding=rounding)
            else:
                amount = base
                allocated += amount
            lines.append({
                'loan_id': self.id,
                'sequence': index,
                'due_date': due,
                'amount': amount,
                'deduction_state': 'pending',
            })
        self.env['hr.loan.installment'].create(lines)

    def _update_deduction_state(self):
        for rec in self:
            rounding = rec.currency_id.rounding
            installments = rec.installment_ids
            if not installments:
                rec.deduction_state = 'pending'
                continue
            if all(i.deduction_state == 'deducted' for i in installments):
                rec.deduction_state = 'deducted'
            elif any(i.deduction_state in ('deducted', 'partial') for i in installments) or \
                    float_compare(rec.amount_deducted, 0.0, precision_rounding=rounding) > 0:
                rec.deduction_state = 'partial'
            elif all(i.skip_next_payslip or i.deduction_state == 'skipped' for i in installments):
                rec.deduction_state = 'skipped'
            else:
                rec.deduction_state = 'pending'

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

    def action_compute_installments_preview(self):
        """Preview schedule while still in draft/approved (before confirm)."""
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('Installments are already generated for confirmed loans.'))
            rec._check_installment_params()
            rec._generate_installments()
        return True

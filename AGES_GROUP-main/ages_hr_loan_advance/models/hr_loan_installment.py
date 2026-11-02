# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class HrLoanInstallment(models.Model):
    _name = 'hr.loan.installment'
    _description = 'Loan Installment'
    _order = 'due_date, sequence, id'

    name = fields.Char(compute='_compute_name', store=True)
    loan_id = fields.Many2one(
        'hr.loan.application', string='Loan', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='loan_id.employee_id', store=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True)
    currency_id = fields.Many2one(related='loan_id.currency_id')
    sequence = fields.Integer(default=10)
    due_date = fields.Date(required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    amount_deducted = fields.Monetary(
        currency_field='currency_id', compute='_compute_deduction', store=True)
    amount_residual = fields.Monetary(
        currency_field='currency_id', compute='_compute_deduction', store=True)
    deduction_state = fields.Selection([
        ('pending', 'Not Deducted'),
        ('partial', 'Partially Deducted'),
        ('deducted', 'Deducted'),
        ('skipped', 'Skipped'),
    ], default='pending', copy=False)
    skip_next_payslip = fields.Boolean(
        string='Skip Next Payslip',
        help='Do not auto-add this installment on the next payslip.')
    payslip_id = fields.Many2one('hr.payslip', string='Payslip', copy=False, readonly=True)
    payslip_input_ids = fields.One2many('hr.payslip.input', 'loan_installment_id', string='Inputs')

    @api.depends('loan_id.name', 'sequence', 'due_date')
    def _compute_name(self):
        for rec in self:
            rec.name = _('%(loan)s — Installment %(seq)s (%(date)s)',
                         loan=rec.loan_id.name or '',
                         seq=rec.sequence,
                         date=rec.due_date or '')

    @api.depends('payslip_input_ids', 'payslip_input_ids.amount', 'payslip_input_ids.payslip_id.state', 'amount')
    def _compute_deduction(self):
        for rec in self:
            done_inputs = rec.payslip_input_ids.filtered(
                lambda l: l.payslip_id.state in ('done', 'paid'))
            deducted = sum(done_inputs.mapped('amount'))
            rec.amount_deducted = deducted
            rec.amount_residual = max(rec.amount - deducted, 0.0)

    def unlink(self):
        if any(i.loan_id.state == 'confirmed' for i in self):
            raise UserError(_('You cannot delete installments of a confirmed loan.'))
        return super().unlink()

    def action_mark_skipped(self):
        self.write({'skip_next_payslip': True, 'deduction_state': 'skipped'})

    def action_resume_deduction(self):
        for rec in self:
            vals = {'skip_next_payslip': False}
            if float_is_zero(rec.amount_residual, precision_rounding=rec.currency_id.rounding):
                vals['deduction_state'] = 'deducted'
            elif float_compare(rec.amount_deducted, 0.0, precision_rounding=rec.currency_id.rounding) > 0:
                vals['deduction_state'] = 'partial'
            else:
                vals['deduction_state'] = 'pending'
            rec.write(vals)

    def _get_pending_amount_for_payslip(self, payslip):
        self.ensure_one()
        if self.loan_id.state != 'confirmed' or self.skip_next_payslip:
            return 0.0
        if self.deduction_state == 'deducted':
            return 0.0
        if self.due_date and self.due_date > payslip.date_to:
            return 0.0
        if float_is_zero(self.amount_residual, precision_rounding=self.currency_id.rounding):
            return 0.0
        return self.amount_residual

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
        loans = self.mapped('loan_id')
        loans._update_deduction_state()

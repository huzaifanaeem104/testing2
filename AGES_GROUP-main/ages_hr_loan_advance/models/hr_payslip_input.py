# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    advance_id = fields.Many2one(
        'hr.advance.application', string='Advance', ondelete='set null', copy=False)
    loan_installment_id = fields.Many2one(
        'hr.loan.installment', string='Loan Installment', ondelete='set null', copy=False)

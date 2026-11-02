# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    advance_count = fields.Integer(compute='_compute_loan_advance_counts')
    loan_count = fields.Integer(compute='_compute_loan_advance_counts')

    def _compute_loan_advance_counts(self):
        Advance = self.env['hr.advance.application']
        Loan = self.env['hr.loan.application']
        for employee in self:
            employee.advance_count = Advance.search_count([('employee_id', '=', employee.id)])
            employee.loan_count = Loan.search_count([('employee_id', '=', employee.id)])

    def action_open_advances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Advances',
            'res_model': 'hr.advance.application',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_open_loans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Loans',
            'res_model': 'hr.loan.application',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

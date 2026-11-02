# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    slip_ids = fields.One2many('hr.payslip', 'employee_id', string='Payslips')
    payslip_count = fields.Integer(compute='_compute_payslip_count')
    salary_attachment_count = fields.Integer(compute='_compute_salary_attachment_count')

    def _compute_payslip_count(self):
        grouped = self.env['hr.payslip']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        mapped = {emp.id: count for emp, count in grouped}
        for employee in self:
            employee.payslip_count = mapped.get(employee.id, 0)

    def _compute_salary_attachment_count(self):
        Attachment = self.env['hr.salary.attachment']
        for employee in self:
            employee.salary_attachment_count = Attachment.search_count([
                ('employee_ids', 'in', employee.id),
            ])

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Payslips',
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

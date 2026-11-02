# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayrollEditPayslipLinesWizard(models.TransientModel):
    _name = 'hr.payroll.edit.payslip.lines.wizard'
    _description = 'Edit Payslip Lines'

    payslip_id = fields.Many2one('hr.payslip', required=True)
    line_ids = fields.One2many('hr.payroll.edit.payslip.line', 'edit_payslip_lines_wizard_id')
    worked_days_line_ids = fields.One2many(
        'hr.payroll.edit.payslip.worked.days.line', 'edit_payslip_lines_wizard_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        payslip = self.env['hr.payslip'].browse(self.env.context.get('default_payslip_id'))
        if payslip:
            res['payslip_id'] = payslip.id
            res['line_ids'] = [(0, 0, {
                'sequence': line.sequence,
                'code': line.code,
                'name': line.name,
                'salary_rule_id': line.salary_rule_id.id,
                'quantity': line.quantity,
                'rate': line.rate,
                'amount': line.amount,
                'total': line.total,
            }) for line in payslip.line_ids]
            res['worked_days_line_ids'] = [(0, 0, {
                'name': wd.name,
                'work_entry_type_id': wd.work_entry_type_id.id,
                'number_of_days': wd.number_of_days,
                'number_of_hours': wd.number_of_hours,
                'amount': wd.amount,
            }) for wd in payslip.worked_days_line_ids]
        return res

    def action_validate_edition(self):
        self.ensure_one()
        slip = self.payslip_id
        slip.line_ids.unlink()
        slip.worked_days_line_ids.unlink()
        for line in self.line_ids:
            self.env['hr.payslip.line'].create({
                'slip_id': slip.id,
                'sequence': line.sequence,
                'code': line.code,
                'name': line.name,
                'salary_rule_id': line.salary_rule_id.id,
                'contract_id': slip.contract_id.id,
                'employee_id': slip.employee_id.id,
                'quantity': line.quantity,
                'rate': line.rate,
                'amount': line.amount,
                'total': line.total,
            })
        for wd in self.worked_days_line_ids:
            self.env['hr.payslip.worked_days'].create({
                'payslip_id': slip.id,
                'name': wd.name,
                'work_entry_type_id': wd.work_entry_type_id.id,
                'number_of_days': wd.number_of_days,
                'number_of_hours': wd.number_of_hours,
                'amount': wd.amount,
            })
        slip.edited = True
        slip.state = 'verify'
        return {'type': 'ir.actions.act_window_close'}


class HrPayrollEditPayslipLine(models.TransientModel):
    _name = 'hr.payroll.edit.payslip.line'
    _description = 'Edit Payslip Line'

    edit_payslip_lines_wizard_id = fields.Many2one('hr.payroll.edit.payslip.lines.wizard', ondelete='cascade')
    sequence = fields.Integer()
    code = fields.Char()
    name = fields.Char()
    salary_rule_id = fields.Many2one('hr.salary.rule')
    quantity = fields.Float(default=1.0)
    rate = fields.Float(default=100.0)
    amount = fields.Float()
    total = fields.Float()


class HrPayrollEditPayslipWorkedDaysLine(models.TransientModel):
    _name = 'hr.payroll.edit.payslip.worked.days.line'
    _description = 'Edit Payslip Worked Days Line'

    edit_payslip_lines_wizard_id = fields.Many2one('hr.payroll.edit.payslip.lines.wizard', ondelete='cascade')
    name = fields.Char()
    work_entry_type_id = fields.Many2one('hr.work.entry.type')
    number_of_days = fields.Float()
    number_of_hours = fields.Float()
    amount = fields.Float()

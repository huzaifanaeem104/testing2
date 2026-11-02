# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayrollStructure(models.Model):
    _name = 'hr.payroll.structure'
    _description = 'Salary Structure'

    @api.model
    def _get_default_report_id(self):
        return self.env.ref('ages_hr_payroll.action_report_payslip', False)

    name = fields.Char(required=True)
    code = fields.Char()
    active = fields.Boolean(default=True)
    type_id = fields.Many2one('hr.payroll.structure.type', required=True)
    country_id = fields.Many2one('res.country', string='Country', default=lambda self: self.env.company.country_id)
    note = fields.Html(string='Description')
    rule_ids = fields.One2many('hr.salary.rule', 'struct_id', copy=True, string='Salary Rules')
    report_id = fields.Many2one(
        'ir.actions.report', string="Template",
        domain="[('model', '=', 'hr.payslip'), ('report_type', '=', 'qweb-pdf')]",
        default=_get_default_report_id,
    )
    payslip_name = fields.Char(string="Payslip Name", translate=True)
    hide_basic_on_pdf = fields.Boolean()
    unpaid_work_entry_type_ids = fields.Many2many(
        'hr.work.entry.type', 'hr_payroll_structure_hr_work_entry_type_rel')
    use_worked_day_lines = fields.Boolean(default=True)
    schedule_pay = fields.Selection(related='type_id.default_schedule_pay')
    input_line_type_ids = fields.Many2many('hr.payslip.input.type', string='Other Input Line')
    ytd_computation = fields.Boolean(default=False, string='Year to Date Computation')

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._("%s (copy)", structure.name)) for structure, vals in zip(self, vals_list)]

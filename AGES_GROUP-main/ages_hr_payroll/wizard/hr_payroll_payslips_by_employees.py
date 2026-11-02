# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipEmployees(models.TransientModel):
    _name = 'hr.payslip.employees'
    _description = 'Generate payslips for all selected employees'

    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True)
    structure_id = fields.Many2one('hr.payroll.structure', string='Salary Structure')

    def get_employees_domain(self):
        return [('company_id', '=', self.env.company.id), ('contract_ids.state', '=', 'open')]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'employee_ids' in fields_list and not res.get('employee_ids'):
            employees = self.env['hr.employee'].search(self.get_employees_domain())
            res['employee_ids'] = [(6, 0, employees.ids)]
        return res

    def compute_sheet(self):
        self.ensure_one()
        if not self.employee_ids:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))
        payslips = self.env['hr.payslip']
        batch = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))
        if self.env.context.get('active_model') == 'hr.payslip.run' and batch:
            date_from = batch.date_start
            date_to = batch.date_end
        else:
            date_from = fields.Date.context_today(self).replace(day=1)
            date_to = fields.Date.end_of(date_from, 'month')
            batch = self.env['hr.payslip.run'].create({
                'name': _('Payslips %s', date_from.strftime('%B %Y')),
                'date_start': date_from,
                'date_end': date_to,
            })
        for employee in self.employee_ids:
            contract = employee.contract_id
            if not contract or contract.state != 'open':
                contracts = self.env['hr.contract'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'open'),
                    ('date_start', '<=', date_to),
                    '|', ('date_end', '=', False), ('date_end', '>=', date_from),
                ], limit=1)
                contract = contracts
            if not contract:
                continue
            structure = self.structure_id or contract.structure_type_id.default_struct_id
            slip = self.env['hr.payslip'].create({
                'employee_id': employee.id,
                'contract_id': contract.id,
                'struct_id': structure.id if structure else False,
                'date_from': date_from,
                'date_to': date_to,
                'payslip_run_id': batch.id,
                'company_id': employee.company_id.id,
            })
            payslips |= slip
        if not payslips:
            raise UserError(_("No open contracts found for the selected employees in this period."))
        payslips.contract_id.generate_work_entries(date_from, date_to)
        payslips.compute_sheet()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'views': [[False, 'form']],
            'res_id': batch.id,
        }

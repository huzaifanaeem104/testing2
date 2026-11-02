# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    @api.onchange('employee_id', 'job_id')
    def _onchange_employee_id_tracking(self):
        if not self.employee_id:
            return

        # Auto fetch Department and Job Position from employee
        if self.employee_id.department_id:
            self.department_id = self.employee_id.department_id
        if self.employee_id.job_id:
            self.job_id = self.employee_id.job_id

        # Auto fetch Wage / Hourly Wage from employee if available
        if hasattr(self.employee_id, 'wage') and self.employee_id.wage:
            if not self.wage or self.wage == 0.0:
                self.wage = self.employee_id.wage
        if hasattr(self.employee_id, 'hourly_wage') and hasattr(self, 'hourly_wage') and self.employee_id.hourly_wage:
            if not self.hourly_wage or self.hourly_wage == 0.0:
                self.hourly_wage = self.employee_id.hourly_wage

        # Auto-fill Contract Reference (name): Employee Name - Job Position - Sequence (if > 1)
        emp_name = self.employee_id.name or ''
        job_name = self.job_id.name if self.job_id else (self.employee_id.job_id.name if self.employee_id.job_id else '')

        domain = [('employee_id', '=', self.employee_id.id)]
        contract_id = self._origin.id if self._origin else self.id
        if contract_id:
            domain.append(('id', '!=', contract_id))

        existing_count = self.env['hr.contract'].search_count(domain)

        ref_parts = [emp_name]
        if job_name:
            ref_parts.append(job_name)
        if existing_count > 0:
            ref_parts.append(str(existing_count + 1))

        self.name = ' - '.join(ref_parts)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('employee_id') and not vals.get('name'):
                employee = self.env['hr.employee'].browse(vals['employee_id'])
                job_id = vals.get('job_id') or employee.job_id.id
                job = self.env['hr.job'].browse(job_id) if job_id else False

                domain = [('employee_id', '=', employee.id)]
                existing_count = self.env['hr.contract'].search_count(domain)

                emp_name = employee.name or ''
                job_name = job.name if job else ''

                ref_parts = [emp_name]
                if job_name:
                    ref_parts.append(job_name)
                if existing_count > 0:
                    ref_parts.append(str(existing_count + 1))

                vals['name'] = ' - '.join(ref_parts)
        return super().create(vals_list)

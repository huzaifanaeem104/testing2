# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _preprocess_work_hours_data(self, work_data, date_from, date_to):
        """
        For hourly contracts sourced from attendances, peel overtime hours out
        of the default work-entry type and push them onto OVERTIME.
        """
        super()._preprocess_work_hours_data(work_data, date_from, date_to)

        if not self.company_id[:1].ages_payroll_attendance_overtime:
            return

        attendance_hourly = self.filtered(
            lambda contract: (
                contract.work_entry_source == 'attendance'
                and getattr(contract, 'wage_type', False) == 'hourly'
            )
        )
        if not attendance_hourly:
            return

        overtime_type = self.env.ref('hr_work_entry.overtime_work_entry_type', raise_if_not_found=False)
        default_types = attendance_hourly.mapped('structure_type_id.default_work_entry_type_id')
        if not overtime_type or len(default_types) != 1 or not default_types:
            return

        # Real Overtime Hours work entries already present — do not peel again
        # (would understate WORK100 and double-count OVERTIME on the payslip).
        if work_data.get(overtime_type.id):
            return

        overtime_hours = self.env['hr.attendance.overtime']._read_group(
            [
                ('employee_id', 'in', self.employee_id.ids),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ],
            [],
            ['duration:sum'],
        )[0][0]
        if not overtime_hours or overtime_hours < 0:
            return

        unapproved = round(self.env['hr.attendance'].sudo()._read_group(
            [
                ('employee_id', 'in', self.employee_id.ids),
                ('check_in', '>=', date_from),
                ('check_out', '<=', date_to),
                ('overtime_hours', '>', 0),
                ('overtime_status', '!=', 'approved'),
            ],
            [],
            ['overtime_hours:sum'],
        )[0][0] or 0.0, 2)

        default_type_id = default_types.id
        work_data[default_type_id] = work_data.get(default_type_id, 0.0) - overtime_hours
        payable_overtime = overtime_hours - unapproved
        if payable_overtime > 0:
            work_data[overtime_type.id] = work_data.get(overtime_type.id, 0.0) + payable_overtime

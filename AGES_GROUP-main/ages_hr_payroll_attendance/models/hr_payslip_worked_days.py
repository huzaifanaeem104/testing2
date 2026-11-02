# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    def _compute_amount(self):
        overtime_type = self.env.ref(
            'hr_work_entry.overtime_work_entry_type', raise_if_not_found=False,
        )
        percent = None
        if 'hr.rule.parameter' in self.env:
            percent = self.env['hr.rule.parameter'].sudo()._get_parameter_from_code(
                'overtime_pay_percent', raise_if_not_found=False,
            )

        if not overtime_type or percent is None or percent == 100:
            return super()._compute_amount()

        factor = percent / 100.0
        overtime_lines = self.env['hr.payslip.worked_days']
        for line in self:
            if line.work_entry_type_id != overtime_type:
                continue
            if getattr(line.payslip_id, 'wage_type', False) != 'hourly':
                continue
            overtime_lines |= line
            if line.is_paid:
                base = line.payslip_id.contract_id.hourly_wage * line.number_of_hours
            else:
                base = 0.0
            line.amount = base * factor

        return super(HrPayslipWorkedDays, self - overtime_lines)._compute_amount()

    def _is_half_day(self):
        self.ensure_one()
        overtime_type = self.env.ref(
            'hr_work_entry.overtime_work_entry_type', raise_if_not_found=False,
        )
        if overtime_type and self.work_entry_type_id == overtime_type:
            return False
        return super()._is_half_day()

# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from datetime import datetime

from odoo import _, models
from odoo.exceptions import ValidationError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _ages_assert_no_deferred_leaves(self):
        if self.env.context.get('salary_simulation'):
            return
        regular = self.filtered(lambda slip: getattr(slip, 'is_regular', True))
        if not regular:
            return

        leaves = self.env['hr.leave'].search([
            ('employee_id', 'in', regular.employee_id.ids),
            ('state', '!=', 'refuse'),
        ])
        blocked = leaves.filtered(lambda leave: leave.payslip_state == 'blocked')
        if blocked:
            raise ValidationError(_(
                'There is remaining time off to defer for: %s',
                ', '.join(blocked.mapped('employee_id.display_name')),
            ))

        max_date = datetime.combine(max(regular.mapped('date_to')), datetime.max.time())
        to_mark = leaves.filtered(
            lambda leave: leave.payslip_state != 'blocked' and leave.date_to <= max_date
        )
        if to_mark:
            to_mark.write({'payslip_state': 'done'})

    def compute_sheet(self):
        self._ages_assert_no_deferred_leaves()
        return super().compute_sheet()

    def action_compute_sheet(self):
        # Compatibility if the payroll engine exposes the classic action name
        if hasattr(super(), 'action_compute_sheet'):
            self._ages_assert_no_deferred_leaves()
            return super().action_compute_sheet()
        return self.compute_sheet()

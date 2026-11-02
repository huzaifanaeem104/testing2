# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _get_resource_calendar_leaves(self, start_dt, end_dt):
        leaves = super()._get_resource_calendar_leaves(start_dt, end_dt)
        return leaves.filtered(
            lambda leave: not leave.holiday_id or leave.holiday_id.payslip_state != 'blocked'
        )

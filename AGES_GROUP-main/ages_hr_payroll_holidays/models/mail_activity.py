# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def _action_done(self, feedback=False, attachment_ids=None):
        leave_acts = self.filtered(lambda act: act.res_model == 'hr.leave' and act.res_id)
        defer_type_id = self.env['ir.model.data']._xmlid_to_res_id(
            'ages_hr_payroll_holidays.mail_activity_data_hr_leave_to_defer',
            raise_if_not_found=False,
        )
        if leave_acts and defer_type_id:
            leave_acts = leave_acts.filtered(lambda act: act.activity_type_id.id == defer_type_id)
            if leave_acts:
                self.env['hr.leave'].browse(leave_acts.mapped('res_id')).write({
                    'payslip_state': 'done',
                })
        return super()._action_done(feedback=feedback, attachment_ids=attachment_ids)

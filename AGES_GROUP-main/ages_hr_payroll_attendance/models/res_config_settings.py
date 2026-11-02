# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_payroll_attendance_overtime = fields.Boolean(
        related='company_id.ages_payroll_attendance_overtime',
        readonly=False,
    )

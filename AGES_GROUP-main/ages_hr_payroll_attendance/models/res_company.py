# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ages_payroll_attendance_overtime = fields.Boolean(
        string='Attendance Overtime on Payslips',
        default=True,
        help='When enabled, approved attendance overtime is separated on '
             'hourly attendance-based payslips.',
    )

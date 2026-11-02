# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    ages_payroll_defer = fields.Boolean(
        string='Allow Payroll Deferral',
        default=True,
        help='When enabled, leaves of this type can be deferred if they overlap '
             'a validated payslip period.',
    )

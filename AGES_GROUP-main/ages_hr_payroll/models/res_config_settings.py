# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_ages_hr_payroll_account = fields.Boolean(string='Payroll Accounting')
    module_ages_hr_payroll_attendance = fields.Boolean(string='Payroll Attendance')
    module_ages_hr_payroll_holidays = fields.Boolean(string='Payroll Time Off')
    module_ages_hr_loan_advance = fields.Boolean(string='Loans & Advances')

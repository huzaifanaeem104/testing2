# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayrollDashboardWarning(models.Model):
    _name = 'hr.payroll.dashboard.warning'
    _description = 'Payroll Dashboard Warning'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    country_id = fields.Many2one('res.country', string='Country')
    evaluation_code = fields.Text(
        string='Python Code',
        default=(
            "# Available variables:\n"
            "# - warning_count, warning_records, warning_action, additional_context\n"
            "# - self (hr.payslip), last_batches, date, datetime, relativedelta, defaultdict\n"
        ),
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Warning Color')

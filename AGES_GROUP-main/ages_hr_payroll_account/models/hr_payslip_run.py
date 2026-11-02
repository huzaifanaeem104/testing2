# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)

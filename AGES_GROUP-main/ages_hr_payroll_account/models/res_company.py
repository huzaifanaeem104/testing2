# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    batch_payroll_move_lines = fields.Boolean(
        string="Batch Payroll Journal Entries",
        help="If enabled, group payslip accounting lines into fewer journal entries.")

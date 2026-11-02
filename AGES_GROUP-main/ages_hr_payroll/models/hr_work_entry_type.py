# -*- coding: utf-8 -*-
from odoo import fields, models


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    round_days = fields.Selection([
        ('NO', 'No Rounding'),
        ('HALF', 'Half Day'),
        ('FULL', 'Day'),
    ], string='Rounding', default='NO')
    round_days_type = fields.Selection([
        ('HALF-UP', 'Closest'),
        ('UP', 'Up'),
        ('DOWN', 'Down'),
    ], string='Rounding Type', default='HALF-UP')

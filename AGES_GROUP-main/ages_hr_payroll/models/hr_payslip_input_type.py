# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipInputType(models.Model):
    _name = 'hr.payslip.input.type'
    _description = 'Payslip Input Type'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    country_id = fields.Many2one('res.country')
    struct_ids = fields.Many2many('hr.payroll.structure', string='Availability in Structure')
    available_in_attachments = fields.Boolean()
    is_quantity = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

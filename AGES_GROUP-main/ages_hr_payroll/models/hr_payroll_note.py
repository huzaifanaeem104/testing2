# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayrollNote(models.Model):
    _name = 'hr.payroll.note'
    _description = 'Payroll Note'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    note = fields.Html()
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

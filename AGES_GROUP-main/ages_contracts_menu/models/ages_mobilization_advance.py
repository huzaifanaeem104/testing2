# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesMobilizationAdvance(models.Model):
    _name = 'ages.mobilization.advance'
    _description = 'Mobilization Advance'
    _rec_name = 'name'
    _order = 'name, id'

    name = fields.Char(string='Reference', required=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

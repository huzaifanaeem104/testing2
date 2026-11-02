# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesSecondaryUom(models.Model):
    _name = 'ages.secondary.uom'
    _description = 'Secondary UOM'
    _order = 'name, id'

    name = fields.Char(string='UOM', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

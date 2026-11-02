# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    ages_material_consumption_id = fields.Many2one(
        comodel_name='ages.material.consumption',
        string='Material Consumption',
        copy=False,
        index=True,
        ondelete='set null',
    )

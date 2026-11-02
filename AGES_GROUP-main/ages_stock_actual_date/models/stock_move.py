# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    actual_date = fields.Date(
        required=False,
        default=fields.Date.context_today,
        readonly=False,
    )

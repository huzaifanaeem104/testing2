# -*- coding: utf-8 -*-
from odoo import fields, models


class StockActualDateMixin(models.AbstractModel):
    _inherit = 'stock.actual.date.mixin'

    actual_date = fields.Date(
        required=False,
        default=fields.Date.context_today,
    )

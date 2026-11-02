# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    barcode_nomenclature_id = fields.Many2one(
        related='company_id.nomenclature_id',
        readonly=False,
        string='Barcode Nomenclature',
    )
    show_barcode_nomenclature = fields.Boolean(default=True)
    group_barcode_show_quantity_count = fields.Boolean(
        string='Show Quantity to Count',
        implied_group='stock_barcode.group_barcode_show_quantity_count',
    )
    group_barcode_count_entire_location = fields.Boolean(
        string='Count Entire Locations',
        implied_group='stock_barcode.group_barcode_count_entire_location',
    )

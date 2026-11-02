# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    barcodelookup_api_key = fields.Char(
        string='Barcode Lookup API Key',
        config_parameter='stock_barcode_barcodelookup.api_key',
    )

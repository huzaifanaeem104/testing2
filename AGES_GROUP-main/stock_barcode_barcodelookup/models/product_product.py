# -*- coding: utf-8 -*-

import json
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _create_from_barcodelookup(self, barcode):
        api_key = self.env['ir.config_parameter'].sudo().get_param('stock_barcode_barcodelookup.api_key')
        if not api_key:
            raise UserError(_(
                'No product found for barcode %s. Set a barcodelookup.com API key in Inventory settings.',
                barcode,
            ))
        url = 'https://api.barcodelookup.com/v3/products?%s' % urlencode({
            'barcode': barcode,
            'key': api_key,
        })
        try:
            with urlopen(url, timeout=15) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as error:
            _logger.warning('Barcode lookup failed for %s: %s', barcode, error)
            raise UserError(_('Could not reach barcodelookup.com for barcode %s.', barcode))
        products = payload.get('products') or []
        if not products:
            raise UserError(_('barcodelookup.com has no product for barcode %s.', barcode))
        info = products[0]
        name = info.get('title') or info.get('brand') or barcode
        return self.create({
            'name': name,
            'barcode': barcode,
            'default_code': barcode,
            'description': info.get('description') or False,
            'is_storable': True,
        })

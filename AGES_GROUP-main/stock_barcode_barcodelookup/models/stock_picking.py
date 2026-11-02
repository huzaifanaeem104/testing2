# -*- coding: utf-8 -*-

from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def process_barcode(self, barcode):
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
        if not product:
            product = self.env['product.product']._create_from_barcodelookup(barcode)
            if self.state in ('assigned', 'confirmed', 'draft'):
                self.move_ids.create({
                    'name': product.display_name,
                    'product_id': product.id,
                    'product_uom_qty': 1,
                    'product_uom': product.uom_id.id,
                    'picking_id': self.id,
                    'location_id': self.location_id.id,
                    'location_dest_id': self.location_dest_id.id,
                })
        return super().process_barcode(barcode)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def process_inventory_barcode(self, barcode, location_id=False):
        location = self.env['stock.location'].search([('barcode', '=', barcode)], limit=1)
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
        if not location and not product and location_id:
            self.env['product.product']._create_from_barcodelookup(barcode)
        return super().process_inventory_barcode(barcode, location_id)

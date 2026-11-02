# -*- coding: utf-8 -*-

from odoo import api, models, _
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def get_inventory_barcode_data(self, location_id=False):
        location = self.env['stock.location'].browse(location_id) if location_id else self.env['stock.location']
        quants = self.env['stock.quant']
        if location and self.env.user.has_group('stock_barcode.group_barcode_count_entire_location'):
            quants = self.search([
                ('location_id', '=', location.id),
                ('quantity', '!=', 0),
            ])
        return {
            'location': location.read(['id', 'name', 'complete_name', 'barcode']) if location else {},
            'show_quantity_count': self.env.user.has_group('stock_barcode.group_barcode_show_quantity_count'),
            'count_entire_location': self.env.user.has_group('stock_barcode.group_barcode_count_entire_location'),
            'lines': [{
                'id': quant.id,
                'product_id': quant.product_id.id,
                'product_name': quant.product_id.display_name,
                'barcode': quant.product_id.barcode or '',
                'qty_expected': quant.quantity if self.env.user.has_group('stock_barcode.group_barcode_show_quantity_count') else False,
                'qty_counted': quant.inventory_quantity,
            } for quant in quants],
        }

    @api.model
    def process_inventory_barcode(self, barcode, location_id=False):
        location = self.env['stock.location'].search([('barcode', '=', barcode)], limit=1)
        if location:
            return self.get_inventory_barcode_data(location.id)

        if not location_id:
            raise UserError(_('Scan a location first, then scan product barcodes.'))
        location = self.env['stock.location'].browse(location_id)
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
        if not product:
            raise UserError(_('No product or location found for barcode %s.', barcode))
        quant = self.search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ], limit=1)
        if not quant:
            quant = self.create({
                'product_id': product.id,
                'location_id': location.id,
                'inventory_quantity': 1,
            })
        else:
            quant.inventory_quantity += 1
        return self.get_inventory_barcode_data(location.id)

    @api.model
    def action_barcode_apply_inventory(self, location_id):
        quants = self.search([
            ('location_id', '=', location_id),
            ('inventory_quantity_set', '=', True),
        ])
        if not quants:
            raise UserError(_('No counted quantities to apply.'))
        return quants.action_apply_inventory()

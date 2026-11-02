# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class StockBarcodeController(http.Controller):

    @http.route('/stock_barcode/print_inventory_commands', type='http', auth='user')
    def print_inventory_commands(self, barcode_type='locations', **kwargs):
        if barcode_type == 'locations':
            locations = request.env['stock.location'].search([('usage', '=', 'internal')])
            return request.redirect(
                '/report/pdf/stock_barcode.action_report_barcode_locations/%s' % ','.join(map(str, locations.ids or [0]))
            )
        picking_types = request.env['stock.picking.type'].search([])
        return request.redirect(
            '/report/pdf/stock_barcode.action_report_barcode_commands/%s' % ','.join(map(str, picking_types.ids or [0]))
        )

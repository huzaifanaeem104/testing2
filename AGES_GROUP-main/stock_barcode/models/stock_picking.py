# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    def action_open_barcode_client(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'stock_barcode_client',
            'name': self.name,
            'context': {
                'active_model': 'stock.picking.type',
                'active_id': self.id,
                'picking_type_id': self.id,
            },
        }


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_open_barcode_client(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'stock_barcode_client',
            'name': self.name,
            'context': {
                'active_model': 'stock.picking',
                'active_id': self.id,
                'picking_id': self.id,
            },
        }

    @api.model
    def get_barcode_data(self, picking_id=False, picking_type_id=False):
        picking = self.browse(picking_id) if picking_id else self.browse()
        picking_type = self.env['stock.picking.type'].browse(picking_type_id) if picking_type_id else picking.picking_type_id
        pickings = self.search([
            ('picking_type_id', '=', picking_type.id),
            ('state', 'in', ('assigned', 'confirmed', 'waiting')),
        ], limit=40) if picking_type and not picking else picking
        return {
            'picking': picking.read(['id', 'name', 'state', 'partner_id', 'location_id', 'location_dest_id']) if picking else {},
            'picking_type': picking_type.read(['id', 'name', 'code']) if picking_type else {},
            'pickings': pickings.read(['id', 'name', 'state', 'partner_id', 'scheduled_date']),
            'lines': picking._get_barcode_lines() if picking else [],
            'show_quantity_count': self.env.user.has_group('stock_barcode.group_barcode_show_quantity_count'),
            'count_entire_location': self.env.user.has_group('stock_barcode.group_barcode_count_entire_location'),
        }

    def _get_barcode_lines(self):
        self.ensure_one()
        lines = []
        for move in self.move_ids.filtered(lambda rec: rec.state != 'cancel'):
            lines.append({
                'id': move.id,
                'product_id': move.product_id.id,
                'product_name': move.product_id.display_name,
                'barcode': move.product_id.barcode or '',
                'qty_demand': move.product_uom_qty,
                'qty_done': move.quantity,
                'uom': move.product_uom.name,
            })
        return lines

    def process_barcode(self, barcode):
        self.ensure_one()
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
        if not product:
            raise UserError(_('No product found for barcode %s.', barcode))
        move = self.move_ids.filtered(lambda rec: rec.product_id == product and rec.state != 'cancel')[:1]
        if not move:
            raise UserError(_('Product %s is not on this transfer.', product.display_name))
        move.quantity += 1
        return self._get_barcode_lines()

    def action_barcode_validate(self):
        self.ensure_one()
        return self.button_validate()

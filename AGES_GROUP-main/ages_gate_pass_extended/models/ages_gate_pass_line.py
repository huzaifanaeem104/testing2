# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesGatePassLine(models.Model):
    _inherit = 'ages.gate.pass.line'

    move_id = fields.Many2one(
        comodel_name='stock.move',
        string='Stock Move',
        copy=False,
        ondelete='set null',
    )
    qty_returned = fields.Float(
        string='Qty Returned',
        digits='Product Unit of Measure',
        default=0.0,
        copy=False,
    )
    remaining_on_transfer = fields.Float(
        string='Remaining on Transfer',
        compute='_compute_remaining_on_transfer',
        digits='Product Unit of Measure',
    )

    @api.depends(
        'product_id',
        'uom_id',
        'gate_pass_id.picking_id',
        'gate_pass_id.picking_ids',
        'confirm_qty',
    )
    def _compute_remaining_on_transfer(self):
        for line in self:
            if not line.gate_pass_id or not line.product_id:
                line.remaining_on_transfer = 0.0
                continue
            remaining = line.gate_pass_id._get_product_remaining_qty(
                line.product_id, line.uom_id,
            )
            line.remaining_on_transfer = remaining if remaining is not None else 0.0

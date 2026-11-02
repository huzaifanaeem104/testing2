# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    ages_require_gate_pass = fields.Boolean(
        string='Require Gate Pass to Validate',
        default=False,
        help='If enabled, transfers of this operation type cannot be '
             'validated (Done) unless they have at least one Gate Pass '
             'that has been Posted (cleared). Enable this for Receipts and '
             'Internal Transfers involving site/warehouse movement; leave '
             'off for operation types that never need a gate control, '
             'e.g. pure stock adjustments.',
    )

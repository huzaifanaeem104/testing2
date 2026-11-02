# -*- coding: utf-8 -*-

from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    purchaser_id = fields.Many2one(
        'hr.employee',
        string='Purchaser',
        tracking=True,
        check_company=True,
        help='Employee responsible for this purchase.',
    )

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.purchaser_id:
            vals['purchaser_id'] = self.purchaser_id.id
        return vals

# -*- coding: utf-8 -*-

from odoo import models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _create_or_update_picking(self):
        """Civil Material receipts come only from slips — not from PO line sync."""
        civil = self.filtered(
            lambda l: l.order_id.is_civil_material
            or self.env.context.get("ages_civil_skip_picking")
        )
        others = self - civil
        if others:
            return super(PurchaseOrderLine, others)._create_or_update_picking()
        return True

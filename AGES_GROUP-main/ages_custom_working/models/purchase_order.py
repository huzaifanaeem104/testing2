from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_id = fields.Many2one(
        domain="[('client_vendor_type', '=', 'vendor')]",
    )

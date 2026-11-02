from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_id = fields.Many2one(
        string="Client",
        domain="[('client_vendor_type', '=', 'client')]",
    )

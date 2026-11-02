from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    client_vendor_type = fields.Selection(
        [('client', 'Client'), ('vendor', 'Vendor')],
        string='Client/Vendor',
    )

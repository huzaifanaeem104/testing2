# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ages_gate_pass_security_required = fields.Boolean(
        string='Gate Pass Security Desk',
        default=True,
        help='If enabled, posting sends the Gate Pass to Waiting Security before Posted.',
    )
    ages_gate_pass_block_qty_overflow = fields.Boolean(
        string='Block Gate Pass Qty Over GRN',
        default=True,
        help='Block confirm quantity that exceeds remaining quantity on linked GRN/Delivery.',
    )
    ages_gate_pass_rgp_default_days = fields.Integer(
        string='RGP Default Return Days',
        default=7,
    )

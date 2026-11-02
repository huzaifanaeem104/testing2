# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_gate_pass_security_required = fields.Boolean(
        related='company_id.ages_gate_pass_security_required',
        readonly=False,
    )
    ages_gate_pass_block_qty_overflow = fields.Boolean(
        related='company_id.ages_gate_pass_block_qty_overflow',
        readonly=False,
    )
    ages_gate_pass_rgp_default_days = fields.Integer(
        related='company_id.ages_gate_pass_rgp_default_days',
        readonly=False,
    )

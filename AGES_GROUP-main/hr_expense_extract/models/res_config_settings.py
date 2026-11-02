# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    expense_extract_mode = fields.Selection(
        related='company_id.expense_extract_mode',
        readonly=False,
        required=True,
    )

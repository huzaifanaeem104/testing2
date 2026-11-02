# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesMobilizationAdvance(models.Model):
    _inherit = 'ages.mobilization.advance'

    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        ondelete='restrict',
        index=True,
    )

# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesRetentionRecovery(models.Model):
    _inherit = 'ages.retention.recovery'

    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        ondelete='restrict',
        index=True,
    )

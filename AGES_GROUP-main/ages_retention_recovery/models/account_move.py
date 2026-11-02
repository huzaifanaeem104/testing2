# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    ages_retention_recovery_id = fields.Many2one(
        comodel_name='ages.retention.recovery',
        string='Retention Recovery',
        copy=False,
        index=True,
    )

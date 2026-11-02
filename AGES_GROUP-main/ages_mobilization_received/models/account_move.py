# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    ages_mobilization_advance_id = fields.Many2one(
        comodel_name='ages.mobilization.advance',
        string='Mobilization Received',
        copy=False,
        index=True,
    )

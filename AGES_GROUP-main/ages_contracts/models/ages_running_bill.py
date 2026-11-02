# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesRunningBill(models.Model):
    _inherit = 'ages.running.bill'

    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        ondelete='restrict',
        index=True,
    )

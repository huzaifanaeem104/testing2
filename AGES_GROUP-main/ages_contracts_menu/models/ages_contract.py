# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesContract(models.Model):
    """Base contract model. Full business logic lives in ages_contracts."""

    _name = 'ages.contract'
    _description = 'Contract'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Contract Number', required=True, default='New', copy=False)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

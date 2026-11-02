# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesRetentionRecovery(models.Model):
    _name = 'ages.retention.recovery'
    _description = 'Retention Recovery'
    _rec_name = 'name'
    _order = 'name, id'

    name = fields.Char(string='Reference', required=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

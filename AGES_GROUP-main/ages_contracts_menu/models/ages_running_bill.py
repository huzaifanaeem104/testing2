# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesRunningBill(models.Model):
    _name = 'ages.running.bill'
    _description = 'Running Bill'
    _rec_name = 'name'
    _order = 'name, id'

    name = fields.Char(string='Reference', required=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

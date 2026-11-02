# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesSubCompany(models.Model):
    _name = 'ages.sub.company'
    _description = 'Sub Company'
    _rec_name = 'name'
    _order = 'name, id'

    name = fields.Char(
        string='Company Name',
        required=True,
    )
    short_code = fields.Char(
        string='Short Code',
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    account_mapping_ids = fields.One2many(
        comodel_name='ages.sub.company.account.mapping',
        inverse_name='sub_company_id',
        string='Account Mapping',
    )

    _sql_constraints = [
        (
            'short_code_company_uniq',
            'unique(short_code, company_id)',
            'Short Code must be unique per company.',
        ),
    ]

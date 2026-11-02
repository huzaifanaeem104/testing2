# -*- coding: utf-8 -*-

from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    ages_contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        copy=False,
        index=True,
    )
    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        copy=False,
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        copy=False,
    )

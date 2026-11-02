# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

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
    ages_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Location',
        copy=False,
    )

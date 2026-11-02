# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

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
        index=True,
    )
    ages_running_bill_id = fields.Many2one(
        comodel_name='ages.running.bill',
        string='Running Bill',
        copy=False,
        index=True,
    )
    ages_sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        copy=False,
        index=True,
    )

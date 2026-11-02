# -*- coding: utf-8 -*-

from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    ages_contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        copy=False,
        index=True,
    )
    ages_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Contract Location',
        copy=False,
    )

# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    deferred_time_off_manager = fields.Many2one(
        comodel_name='res.users',
        string='Deferred Time Off Responsible',
    )

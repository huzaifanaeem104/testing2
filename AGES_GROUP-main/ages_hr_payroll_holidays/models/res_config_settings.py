# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    deferred_time_off_manager = fields.Many2one(
        related='company_id.deferred_time_off_manager',
        readonly=False,
        check_company=True,
    )

# -*- coding: utf-8 -*-

from odoo import fields, models

from .constants import PARAM_ENABLED


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_deletion_audit_enabled = fields.Boolean(
        string='Log deleted business records',
        config_parameter=PARAM_ENABLED,
        default=True,
        help='When a meaningful business record is deleted, keep who deleted it, '
             'which record it was, and a useful snapshot from before the deletion.',
    )

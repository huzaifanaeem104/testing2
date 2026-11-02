# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    je_access_draft = fields.Boolean(
        string='Draft',
        help='User can create Journal Entries and save them in Draft. '
             'Cannot validate or post.',
    )
    je_access_validate = fields.Boolean(
        string='Validate',
        help='User can create Journal Entries and validate entries that '
             'are in Draft. Can also revoke a validated entry back to Draft.',
    )
    je_access_post = fields.Boolean(
        string='Approved',
        help='User can create Journal Entries, validate and post entries '
             'that are in Validation. Can also revoke a posted entry back '
             'to Validation.',
    )

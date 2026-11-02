# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    purchaser_id = fields.Many2one(
        'hr.employee',
        string='Purchaser',
        tracking=True,
        check_company=True,
        help='Employee responsible for this vendor bill.',
        copy=False,
    )

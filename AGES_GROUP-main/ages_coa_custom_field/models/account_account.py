# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    _inherit = 'account.account'

    main_account = fields.Selection(
        selection=[
            ('EQUITY', 'Equity'),
            ('LIABILITIES', 'Liabilities'),
            ('INCOME', 'Income'),
            ('EXPENSE', 'Expense'),
        ],
        string='Main Account',
        help='High-level financial statement grouping used for reporting.',
    )
    transactional_level = fields.Integer(
        string='Transactional Level',
        help='Account hierarchy depth: 1=section, 2=sub-section, 3=group, 4=posting account, 5=exception.',
    )

    @api.constrains('transactional_level')
    def _check_transactional_level(self):
        for account in self:
            if account.transactional_level and account.transactional_level not in range(1, 6):
                raise ValidationError(
                    'Transactional Level must be between 1 and 5.'
                )

# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    expense_extract_mode = fields.Selection(
        [
            ('no', 'Do not digitize'),
            ('manual', 'Digitize on demand only'),
            ('auto', 'Digitize automatically'),
        ],
        string='Expense Digitalization',
        default='manual',
    )

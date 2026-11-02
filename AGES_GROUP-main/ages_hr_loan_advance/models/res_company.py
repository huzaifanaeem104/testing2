# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    advance_journal_id = fields.Many2one(
        'account.journal',
        string='Advance Journal',
        domain="[('company_id', '=', id), ('type', 'in', ('cash', 'bank', 'general'))]",
        check_company=True,
    )
    advance_receivable_account_id = fields.Many2one(
        'account.account',
        string='Advance Receivable Account',
        domain="[('deprecated', '=', False), ('account_type', 'in', ('asset_receivable', 'asset_current', 'asset_cash'))]",
        check_company=True,
    )
    advance_payment_account_id = fields.Many2one(
        'account.account',
        string='Advance Payment Account',
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help='Default cash/bank account credited when disbursing an advance.',
    )
    loan_journal_id = fields.Many2one(
        'account.journal',
        string='Loan Journal',
        domain="[('company_id', '=', id), ('type', 'in', ('cash', 'bank', 'general'))]",
        check_company=True,
    )
    loan_receivable_account_id = fields.Many2one(
        'account.account',
        string='Loan Receivable Account',
        domain="[('deprecated', '=', False), ('account_type', 'in', ('asset_receivable', 'asset_current', 'asset_cash'))]",
        check_company=True,
    )
    loan_payment_account_id = fields.Many2one(
        'account.account',
        string='Loan Payment Account',
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help='Default cash/bank account credited when disbursing a loan.',
    )

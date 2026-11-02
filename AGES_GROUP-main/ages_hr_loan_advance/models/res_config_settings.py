# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advance_journal_id = fields.Many2one(
        related='company_id.advance_journal_id', readonly=False, check_company=True)
    advance_receivable_account_id = fields.Many2one(
        related='company_id.advance_receivable_account_id', readonly=False, check_company=True)
    advance_payment_account_id = fields.Many2one(
        related='company_id.advance_payment_account_id', readonly=False, check_company=True)
    loan_journal_id = fields.Many2one(
        related='company_id.loan_journal_id', readonly=False, check_company=True)
    loan_receivable_account_id = fields.Many2one(
        related='company_id.loan_receivable_account_id', readonly=False, check_company=True)
    loan_payment_account_id = fields.Many2one(
        related='company_id.loan_payment_account_id', readonly=False, check_company=True)

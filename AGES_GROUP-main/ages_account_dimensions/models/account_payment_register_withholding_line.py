# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountPaymentRegisterWithholdingLine(models.TransientModel):
    _inherit = 'account.payment.register.withholding.line'

    @api.depends('company_id', 'tax_id')
    def _compute_account_id(self):
        """Fill Account from the withholding tax, not the company base-account setting."""
        for line in self:
            account = line._ages_get_default_withholding_account()
            line.account_id = account or line.account_id or False

    @api.depends('payment_register_id.amount', 'payment_register_id.can_edit_wizard')
    def _compute_comodel_percentage_paid_factor(self):
        """Keep the AGES WTH base fixed when the payment amount is changed."""
        ages_lines = self.filtered(
            lambda line: line.payment_register_id._ages_has_source_document()
        )
        ages_lines.comodel_percentage_paid_factor = 1.0
        super(AccountPaymentRegisterWithholdingLine, self - ages_lines)._compute_comodel_percentage_paid_factor()

    def _calc_wht_tax_amount(self, tax, base_amount, currency=None):
        """Calculate withholding tax amount from base amount and tax definition."""
        if not tax or not base_amount:
            return 0.0
        base_amount = abs(base_amount)
        if tax.amount_type == 'percent':
            tax_amount = abs(base_amount * (tax.amount or 0.0) / 100.0)
        elif tax.amount_type == 'division':
            tax_amount = abs(base_amount * ((tax.amount or 0.0) / (100.0 - (tax.amount or 0.0))))
        elif tax.amount_type == 'fixed':
            tax_amount = abs(tax.amount or 0.0)
        else:
            res = tax.compute_all(base_amount, currency=currency, quantity=1.0)
            tax_amount = sum(abs(t['amount']) for t in res.get('taxes', []))
        if currency:
            tax_amount = currency.round(tax_amount)
        return tax_amount

    @api.onchange('base_amount')
    def _onchange_base_amount_ages(self):
        """When user manually updates base_amount, preserve it and re-calculate tax amount."""
        for line in self:
            if line.base_amount:
                line.source_base_amount_currency = line.base_amount
                line.source_base_amount = line.base_amount
                line.original_base_amount = line.base_amount
                if line.tax_id:
                    calc_amt = line._calc_wht_tax_amount(line.tax_id, line.base_amount, line.comodel_currency_id)
                    line.amount = calc_amt
                    line.source_tax_amount_currency = calc_amt
                    line.source_tax_amount = calc_amt
                    line.original_tax_amount = calc_amt

    @api.onchange('tax_id')
    def _onchange_tax_id_ages(self):
        """When user changes tax_id, fill Account and recompute tax on the current base."""
        for line in self:
            account = line._ages_get_default_withholding_account()
            if account:
                line.account_id = account
            current_base = line.base_amount or line.source_base_amount_currency or 0.0
            if current_base and line.tax_id:
                line.base_amount = current_base
                line.source_base_amount_currency = current_base
                line.source_base_amount = current_base
                line.original_base_amount = current_base
                calc_amt = line._calc_wht_tax_amount(line.tax_id, current_base, line.comodel_currency_id)
                line.amount = calc_amt
                line.source_tax_amount_currency = calc_amt
                line.source_tax_amount = calc_amt
                line.original_tax_amount = calc_amt

    @api.depends(
        'source_base_amount_currency',
        'source_base_amount',
        'source_tax_amount_currency',
        'source_tax_amount',
        'source_currency_id',
        'comodel_currency_id',
        'company_id',
        'comodel_date',
        'tax_id',
        'base_amount',
    )
    def _compute_original_amounts(self):
        """Ensure original_base_amount and original_tax_amount reflect user edits on base_amount and tax_id."""
        super()._compute_original_amounts()
        for line in self:
            if line.base_amount and line.base_amount > 0:
                line.original_base_amount = line.base_amount
                line.source_base_amount_currency = line.base_amount
                line.source_base_amount = line.base_amount
                if line.tax_id:
                    calc_amt = line._calc_wht_tax_amount(line.tax_id, line.base_amount, line.comodel_currency_id)
                    line.original_tax_amount = calc_amt
                    line.source_tax_amount_currency = calc_amt
                    line.source_tax_amount = calc_amt

    @api.depends('tax_id', 'base_amount', 'comodel_currency_id')
    def _compute_amount(self):
        """Compute the tax amount directly using tax_id applied to current base_amount."""
        super()._compute_amount()
        for line in self:
            if line.tax_id and line.base_amount:
                line.amount = line._calc_wht_tax_amount(line.tax_id, line.base_amount, line.comodel_currency_id)


class AccountPaymentWithholdingLine(models.Model):
    _inherit = 'account.payment.withholding.line'

    @api.depends('company_id', 'tax_id')
    def _compute_account_id(self):
        for line in self:
            account = line._ages_get_default_withholding_account()
            line.account_id = account or line.account_id or False

    @api.onchange('tax_id')
    def _onchange_tax_id_ages_payment_account(self):
        for line in self:
            account = line._ages_get_default_withholding_account()
            if account:
                line.account_id = account


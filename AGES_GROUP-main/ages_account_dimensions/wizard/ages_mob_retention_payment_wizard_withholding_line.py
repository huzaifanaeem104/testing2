# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesMobRetentionPaymentWizardWithholdingLine(models.TransientModel):
    _name = 'ages.mob.retention.payment.wizard.withholding.line'
    _inherit = 'account.withholding.line'
    _description = 'Mobilization / Retention Payment Withholding Line'

    wizard_id = fields.Many2one(
        comodel_name='ages.mob.retention.payment.wizard',
        required=True,
        ondelete='cascade',
    )

    @api.depends('company_id', 'tax_id')
    def _compute_account_id(self):
        for line in self:
            account = line._ages_get_default_withholding_account()
            line.account_id = account or line.account_id or False

    @api.depends('wizard_id.payment_type')
    def _compute_type_tax_use(self):
        for line in self:
            if line.tax_id:
                line.type_tax_use = line.tax_id.type_tax_use
            else:
                line.type_tax_use = 'sale'

    @api.depends('wizard_id.amount')
    def _compute_comodel_percentage_paid_factor(self):
        # Keep AGES WHT base fixed when the payment amount changes (same as Running Bill).
        self.comodel_percentage_paid_factor = 1.0

    @api.depends('wizard_id.payment_date')
    def _compute_comodel_date(self):
        for line in self:
            line.comodel_date = line.wizard_id.payment_date

    @api.depends('wizard_id.payment_type')
    def _compute_comodel_payment_type(self):
        for line in self:
            line.comodel_payment_type = line.wizard_id.payment_type

    @api.depends('wizard_id.company_id')
    def _compute_company_id(self):
        for line in self:
            line.company_id = line.wizard_id.company_id

    @api.depends('wizard_id.currency_id')
    def _compute_comodel_currency_id(self):
        for line in self:
            line.comodel_currency_id = line.wizard_id.currency_id

    def _calc_wht_tax_amount(self, tax, base_amount, currency=None):
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
        for line in self:
            if line.base_amount:
                line.source_base_amount_currency = line.base_amount
                line.source_base_amount = line.base_amount
                line.original_base_amount = line.base_amount
                if line.tax_id:
                    calc_amt = line._calc_wht_tax_amount(
                        line.tax_id, line.base_amount, line.comodel_currency_id
                    )
                    line.amount = calc_amt
                    line.source_tax_amount_currency = calc_amt
                    line.source_tax_amount = calc_amt
                    line.original_tax_amount = calc_amt

    @api.onchange('tax_id')
    def _onchange_tax_id_ages(self):
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
                calc_amt = line._calc_wht_tax_amount(
                    line.tax_id, current_base, line.comodel_currency_id
                )
                line.amount = calc_amt
                line.source_tax_amount_currency = calc_amt
                line.source_tax_amount = calc_amt
                line.original_tax_amount = calc_amt

    @api.depends('tax_id', 'base_amount', 'comodel_currency_id')
    def _compute_amount(self):
        super()._compute_amount()
        for line in self:
            if line.tax_id and line.base_amount:
                line.amount = line._calc_wht_tax_amount(
                    line.tax_id, line.base_amount, line.comodel_currency_id
                )

    def _get_valid_liquidity_accounts(self):
        return (
            self.wizard_id.journal_id.default_account_id
            | self.wizard_id.payment_method_line_id.payment_account_id
            | self.wizard_id.journal_id.inbound_payment_method_line_ids.payment_account_id
            | self.wizard_id.journal_id.outbound_payment_method_line_ids.payment_account_id
        )

    def _get_comodel_partner(self):
        return self.wizard_id.partner_id

    def _prepare_withholding_amls_create_values(self):
        assert len(self.wizard_id) == 1, self.env._(
            'All withholding lines in self must have the same payment wizard.'
        )
        return super()._prepare_withholding_amls_create_values()

# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class AgesMobRetentionPaymentWizard(models.TransientModel):
    _name = 'ages.mob.retention.payment.wizard'
    _description = 'Receive Mobilization / Retention Payment'

    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.context_today,
    )
    payment_type = fields.Selection(
        selection=[
            ('outbound', 'Send Money'),
            ('inbound', 'Receive Money'),
        ],
        default='inbound',
        required=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Payment Journal',
        required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    payment_method_line_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Payment Method',
        compute='_compute_payment_method_line_id',
        store=True,
        readonly=False,
        domain="[('id', 'in', available_payment_method_line_ids)]",
    )
    available_payment_method_line_ids = fields.Many2many(
        comodel_name='account.payment.method.line',
        compute='_compute_available_payment_method_line_ids',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        readonly=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
    )
    amount_remaining = fields.Monetary(
        string='Remaining',
        readonly=True,
        currency_field='currency_id',
    )
    communication = fields.Char(string='Memo')

    ages_sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        required=True,
        check_company=True,
    )
    ages_contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        readonly=True,
    )
    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        readonly=True,
        check_company=True,
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        readonly=True,
        check_company=True,
    )
    ages_mobilization_advance_id = fields.Many2one(
        comodel_name='ages.mobilization.advance',
        string='Mobilization Received',
        readonly=True,
    )
    ages_retention_recovery_id = fields.Many2one(
        comodel_name='ages.retention.recovery',
        string='Retention Recovery',
        readonly=True,
    )

    display_withholding = fields.Boolean(compute='_compute_display_withholding')
    should_withhold_tax = fields.Boolean(
        string='Withhold Tax Amounts',
        help='Withhold tax amounts from the payment amount.',
        default=False,
    )
    withholding_line_ids = fields.One2many(
        comodel_name='ages.mob.retention.payment.wizard.withholding.line',
        inverse_name='wizard_id',
        string='Withholding Lines',
    )
    withholding_hide_tax_base_account = fields.Boolean(
        compute='_compute_withholding_hide_tax_base_account',
    )
    withholding_net_amount = fields.Monetary(
        string='Net Amount',
        help='Net amount after deducting the withholding lines',
        compute='_compute_withholding_net_amount',
        currency_field='currency_id',
    )
    withholding_payment_account_id = fields.Many2one(
        related='payment_method_line_id.payment_account_id',
    )

    @api.depends('company_id')
    def _compute_display_withholding(self):
        for wizard in self:
            if not wizard.company_id:
                wizard.display_withholding = False
                continue
            withholding_taxes = self.env['account.tax'].search([
                *self.env['account.tax']._check_company_domain(wizard.company_id),
                ('is_withholding_tax_on_payment', '=', True),
                ('type_tax_use', '=', 'sale'),
            ], limit=1)
            wizard.display_withholding = bool(withholding_taxes)

    @api.depends('company_id')
    def _compute_withholding_hide_tax_base_account(self):
        for wizard in self:
            wizard.withholding_hide_tax_base_account = bool(
                wizard.company_id.withholding_tax_base_account_id
            )

    @api.depends('withholding_line_ids.amount', 'amount', 'should_withhold_tax')
    def _compute_withholding_net_amount(self):
        for wizard in self:
            if wizard.should_withhold_tax:
                wizard.withholding_net_amount = wizard.amount - sum(
                    wizard.withholding_line_ids.mapped('amount')
                )
            else:
                wizard.withholding_net_amount = wizard.amount or 0.0

    @api.depends('journal_id')
    def _compute_available_payment_method_line_ids(self):
        for wizard in self:
            if wizard.journal_id:
                wizard.available_payment_method_line_ids = (
                    wizard.journal_id._get_available_payment_method_lines('inbound')
                )
            else:
                wizard.available_payment_method_line_ids = False

    @api.depends('available_payment_method_line_ids')
    def _compute_payment_method_line_id(self):
        for wizard in self:
            if wizard.payment_method_line_id in wizard.available_payment_method_line_ids:
                continue
            wizard.payment_method_line_id = wizard.available_payment_method_line_ids[:1]

    @api.onchange('withholding_line_ids')
    def _onchange_withholding_line_ids(self):
        self.ensure_one()
        if self.withholding_line_ids and not self.should_withhold_tax:
            self.should_withhold_tax = True

    @api.model
    def _ages_default_bank_journal(self, company):
        return self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model
    def _ages_calc_wht_amount(self, tax, base_amount, currency):
        if not tax or not base_amount:
            return 0.0
        base_amount = abs(base_amount)
        if tax.amount_type == 'fixed':
            tax_amount = abs(tax.amount or 0.0)
        else:
            tax_amount = abs(base_amount * (tax.amount or 0.0) / 100.0)
        return currency.round(tax_amount) if currency else tax_amount

    @api.model
    def _ages_prepare_withholding_line_vals(self, tax, base_amount, tax_amount, currency, company):
        base_amount = abs(base_amount or 0.0)
        tax_amount = abs(tax_amount or 0.0)
        if not tax_amount:
            tax_amount = self._ages_calc_wht_amount(tax, base_amount, currency)
        if not tax or not tax_amount:
            return False
        account = (
            self.env['account.withholding.line']._ages_account_from_tax(tax)
            or company.withholding_tax_base_account_id
        )
        vals = {
            'name': tax.name,
            'tax_id': tax.id,
            'source_tax_id': tax.id,
            'source_currency_id': currency.id,
            'source_base_amount_currency': base_amount,
            'source_base_amount': base_amount,
            'source_tax_amount_currency': tax_amount,
            'source_tax_amount': tax_amount,
            'base_amount': base_amount,
            'amount': tax_amount,
            'placeholder_type': 'not_defined',
            'previous_placeholder_type': 'not_defined',
        }
        if account:
            vals['account_id'] = account.id
        return vals

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        mob = self.env['ages.mobilization.advance']
        ret = self.env['ages.retention.recovery']
        if ctx.get('default_ages_mobilization_advance_id'):
            mob = mob.browse(ctx['default_ages_mobilization_advance_id']).exists()
        if ctx.get('default_ages_retention_recovery_id'):
            ret = ret.browse(ctx['default_ages_retention_recovery_id']).exists()

        source = mob or ret
        if not source:
            return res

        remaining = source.amount_remaining if 'amount_remaining' in source._fields else (
            (source.mobilization_amount if mob else source.retention_amount)
            - (getattr(source, 'amount_paid', 0.0) or 0.0)
        )
        company = source.company_id
        currency = source.currency_id
        journal = self._ages_default_bank_journal(company)
        amount = max(remaining, 0.0)
        wht_on = bool(mob and source.wht_on_mobilization) or bool(ret and source.wht_on_retention)

        res.update({
            'payment_type': 'inbound',
            'company_id': company.id,
            'currency_id': currency.id,
            'partner_id': source.partner_id.id,
            'amount': amount,
            'amount_remaining': amount,
            'communication': source.name,
            'ages_sub_company_id': source.sub_company_id.id,
            'ages_contract_id': source.contract_id.id,
            'ages_project_id': source.project_id.id,
            'ages_analytic_account_id': source.analytic_account_id.id,
            'ages_mobilization_advance_id': mob.id if mob else False,
            'ages_retention_recovery_id': ret.id if ret else False,
            'journal_id': journal.id if journal else False,
            'should_withhold_tax': wht_on,
        })

        if wht_on and source.wth_tax_id:
            # Prefill with remaining WHT capacity (document total - already posted).
            doc_wht = abs(source.wth_amount or 0.0)
            posted_wht = source._ages_sum_posted_withholding()
            remaining_wht = max(doc_wht - posted_wht, 0.0)
            base_amount = amount
            tax_amount = remaining_wht
            if remaining_wht and amount and doc_wht:
                # Prefer remaining WHT; if paying partial of document, scale down further.
                doc_base = (
                    source.mobilization_amount if mob else source.retention_amount
                ) or 0.0
                if doc_base and abs(doc_base - amount) > currency.rounding:
                    scaled = currency.round(doc_wht * (amount / doc_base))
                    tax_amount = min(remaining_wht, scaled)
            line_vals = self._ages_prepare_withholding_line_vals(
                source.wth_tax_id, base_amount, tax_amount, currency, company,
            )
            if line_vals and tax_amount:
                res['withholding_line_ids'] = [Command.create(line_vals)]
            elif not remaining_wht:
                res['should_withhold_tax'] = False

        return res

    def _ages_wizard_wht_amount_for_taxes(self, taxes):
        self.ensure_one()
        if not taxes:
            return 0.0
        tax_ids = set(taxes.ids)
        total = 0.0
        for line in self.withholding_line_ids:
            line_taxes = line.tax_id
            if 'source_tax_id' in line._fields and line.source_tax_id:
                line_taxes |= line.source_tax_id
            if line_taxes.ids and tax_ids.intersection(line_taxes.ids):
                total += abs(line.amount or 0.0)
        return total

    def _ages_check_withholding_against_document(self):
        """Block recording more WHT than the mobilization / retention document total."""
        self.ensure_one()
        if not self.should_withhold_tax:
            return
        source = self.ages_mobilization_advance_id or self.ages_retention_recovery_id
        if not source or not source.wth_tax_id:
            return
        currency = self.currency_id or self.company_id.currency_id
        rounding = currency.rounding or 0.01
        actual = abs(source.wth_amount or 0.0)
        posted_amount = source._ages_sum_posted_withholding()
        current = self._ages_wizard_wht_amount_for_taxes(source.wth_tax_id)
        recorded = posted_amount + current
        if float_compare(recorded, actual, precision_rounding=rounding) > 0:
            raise UserError(_(
                'Recorded WHT Amount (%(recorded)s) cannot exceed the document '
                'WHT amount (%(actual)s). Remaining available: %(remaining)s.',
                recorded=currency.format(recorded),
                actual=currency.format(actual),
                remaining=currency.format(max(actual - posted_amount, 0.0)),
            ))

    def _ages_prepare_payment_withholding_commands(self):
        self.ensure_one()
        if not self.should_withhold_tax or not self.withholding_line_ids:
            return []
        commands = []
        PaymentWht = self.env['account.payment.withholding.line']
        for line in self.withholding_line_ids:
            if float_is_zero(line.amount, precision_rounding=self.currency_id.rounding):
                continue
            vals = {
                'name': line.name or line.tax_id.name,
                'tax_id': line.tax_id.id,
                'source_currency_id': (line.source_currency_id or self.currency_id).id,
                'source_base_amount_currency': line.source_base_amount_currency or line.base_amount,
                'source_base_amount': line.source_base_amount or line.base_amount,
                'source_tax_amount_currency': line.source_tax_amount_currency or line.amount,
                'source_tax_amount': line.source_tax_amount or line.amount,
                'base_amount': line.base_amount,
                'amount': line.amount,
                'placeholder_type': line.placeholder_type or 'not_defined',
                'previous_placeholder_type': line.previous_placeholder_type or 'not_defined',
            }
            if line.account_id:
                vals['account_id'] = line.account_id.id
            if 'source_tax_id' in PaymentWht._fields:
                vals['source_tax_id'] = (line.source_tax_id or line.tax_id).id
            if line.analytic_distribution:
                vals['analytic_distribution'] = line.analytic_distribution
            commands.append(Command.create(vals))
        return commands

    def action_create_payment(self):
        self.ensure_one()
        if not self.ages_sub_company_id:
            raise UserError(_('Active Company is required.'))
        if not self.journal_id:
            raise UserError(_('Please select a Payment Journal.'))
        if not self.payment_method_line_id:
            raise UserError(_('Please select a Payment Method.'))

        source = self.ages_mobilization_advance_id or self.ages_retention_recovery_id
        if not source:
            raise UserError(_('No Mobilization / Retention document linked.'))
        if source.state != 'confirmed':
            raise UserError(_('Payments can only be registered on Confirmed documents.'))

        remaining = source.amount_remaining
        rounding = self.currency_id.rounding or 0.01
        if float_compare(self.amount, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_('Payment amount must be greater than zero.'))
        if float_compare(self.amount, remaining, precision_rounding=rounding) > 0:
            raise UserError(_(
                'Payment amount (%(amount)s) cannot exceed the remaining amount (%(remaining)s).',
                amount=self.currency_id.format(self.amount),
                remaining=self.currency_id.format(remaining),
            ))

        if self.should_withhold_tax and self.withholding_line_ids:
            if float_compare(self.withholding_net_amount, 0.0, precision_rounding=rounding) < 0:
                raise UserError(_('The withholding net amount cannot be negative.'))
        self._ages_check_withholding_against_document()

        counterpart = source._ages_get_payment_counterpart_account()
        if not counterpart:
            raise UserError(_(
                'Please configure the Mobilization / Retention account in '
                'Project → Configuration → Settings → Default Accounts.'
            ))

        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'payment_method_line_id': self.payment_method_line_id.id,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'memo': self.communication or source.name,
            'destination_account_id': counterpart.id,
            'ages_sub_company_id': self.ages_sub_company_id.id,
            'ages_contract_id': self.ages_contract_id.id,
            'ages_project_id': self.ages_project_id.id,
            'ages_analytic_account_id': self.ages_analytic_account_id.id,
            'ages_mobilization_advance_id': self.ages_mobilization_advance_id.id,
            'ages_retention_recovery_id': self.ages_retention_recovery_id.id,
        }
        wht_commands = self._ages_prepare_payment_withholding_commands()
        if wht_commands:
            payment_vals['should_withhold_tax'] = True
            payment_vals['withholding_line_ids'] = wht_commands

        payment = self.env['account.payment'].create(payment_vals)
        payment.destination_account_id = counterpart
        payment.action_post()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

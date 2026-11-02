# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    ages_sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    ages_contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
    )
    ages_project_wise_contract = fields.Char(
        related='ages_contract_id.project_wise_name',
        string='Project-Wise Contract',
        readonly=True,
        related_sudo=True,
    )
    ages_contract_description = fields.Text(
        related='ages_contract_id.contract_description',
        string='Contract Description',
        readonly=True,
        related_sudo=True,
    )
    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        check_company=True,
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
    )
    ages_running_bill_id = fields.Many2one(
        comodel_name='ages.running.bill',
        string='Running Bill',
        readonly=True,
    )
    ages_mobilization_advance_id = fields.Many2one(
        comodel_name='ages.mobilization.advance',
        string='Mobilization Advance',
        readonly=True,
    )
    ages_retention_recovery_id = fields.Many2one(
        comodel_name='ages.retention.recovery',
        string='Retention Receive',
        readonly=True,
    )
    ages_wht_autofill_done = fields.Boolean(
        string='AGES WHT Autofill Done',
        default=False,
        copy=False,
    )
    ages_actual_amount = fields.Monetary(
        string='Actual Amount',
        currency_field='currency_id',
        help='Bank amount before withholding. Amount below is '
             'Actual Amount / (100 − WTH %) × 100.',
    )
    ages_show_actual_amount = fields.Boolean(
        compute='_compute_ages_show_actual_amount',
    )

    @api.depends(
        'ages_running_bill_id',
        'ages_running_bill_id.wth_tax_id',
        'ages_running_bill_id.contract_id.wth_tax_id',
        'line_ids',
        'line_ids.move_id.ages_running_bill_id',
    )
    def _compute_ages_show_actual_amount(self):
        for wizard in self:
            bill = wizard._ages_get_single_running_bill()
            wizard.ages_show_actual_amount = bool(
                bill and wizard._ages_bill_wht_tax(bill)
            )

    def _ages_payment_lines_without_retention(self, lines):
        """Keep trade receivable/payable lines for the Pay wizard.

        Excludes:
        - vendor-bill retention hold lines
        - running-bill client hold receivables (Retention / Mobilization AR), which
          use a different account and would split the wizard into multiple batches.
          Multiple batches disable WHT + editable Actual Amount (can_edit_wizard=False).
        """
        lines = lines.filtered(lambda line: not getattr(line, 'ages_is_vendor_retention_line', False))
        if not lines:
            return lines

        hold_accounts = self.env['account.account']
        for company in lines.company_id:
            ret = company.ages_retention_account_id
            if ret and ret.account_type == 'asset_receivable':
                hold_accounts |= ret
            mob = company.ages_mobilization_account_id
            if mob and mob.account_type == 'asset_receivable':
                hold_accounts |= mob
        if not hold_accounts:
            return lines

        ra_moves = lines.move_id.filtered(
            lambda move: bool(getattr(move, 'ages_running_bill_id', False))
        )
        if not ra_moves:
            return lines

        trade_lines = lines.filtered(
            lambda line: line.account_id not in hold_accounts or line.move_id not in ra_moves
        )
        # Never leave the wizard with no lines to pay.
        return trade_lines if trade_lines else lines

    def _ages_get_source_moves(self):
        """Return invoice/bill moves linked to this payment wizard."""
        self.ensure_one()
        moves = self.line_ids.move_id
        if moves:
            return moves
        move_ids = self.env.context.get('active_ids') or []
        if self.env.context.get('active_model') == 'account.move' and move_ids:
            return self.env['account.move'].browse(move_ids).exists()
        if self.env.context.get('active_model') == 'account.move.line' and move_ids:
            return self.env['account.move.line'].browse(move_ids).exists().mapped('move_id')
        return self.env['account.move']

    @api.model
    def _ages_values_from_moves(self, moves):
        """Build Active Company / Project / Analytic / linked-doc defaults from moves."""
        values = {}
        if not moves:
            return values

        sub_companies = moves.mapped('ages_sub_company_id')
        contracts = moves.mapped('ages_contract_id')
        projects = moves.mapped('ages_project_id')
        analytics = moves.mapped('ages_analytic_account_id')
        running_bills = moves.mapped('ages_running_bill_id')
        mobilizations = moves.mapped('ages_mobilization_advance_id')
        retentions = moves.mapped('ages_retention_recovery_id')

        if len(sub_companies) == 1:
            values['ages_sub_company_id'] = sub_companies.id
        if len(contracts) == 1:
            values['ages_contract_id'] = contracts.id
        if len(projects) == 1:
            values['ages_project_id'] = projects.id
        if len(analytics) == 1:
            values['ages_analytic_account_id'] = analytics.id
        elif len(projects) == 1 and projects.account_id:
            values['ages_analytic_account_id'] = projects.account_id.id

        # Fallback Active Company / Contract from project
        if not values.get('ages_sub_company_id') and len(projects) == 1:
            sub_company = self._ages_sub_company_from_project(projects)
            if sub_company:
                values['ages_sub_company_id'] = sub_company.id
            elif projects.ages_contract_id and projects.ages_contract_id.sub_company_id:
                values['ages_sub_company_id'] = projects.ages_contract_id.sub_company_id.id
        if not values.get('ages_contract_id') and len(projects) == 1 and projects.ages_contract_id:
            values['ages_contract_id'] = projects.ages_contract_id.id

        # Fallback from linked running bill / mobilization / retention
        if len(running_bills) == 1:
            values['ages_running_bill_id'] = running_bills.id
            bill = running_bills
            if not values.get('ages_contract_id') and bill.contract_id:
                values['ages_contract_id'] = bill.contract_id.id
            if not values.get('ages_sub_company_id') and bill.sub_company_id:
                values['ages_sub_company_id'] = bill.sub_company_id.id
            if not values.get('ages_project_id') and bill.project_id:
                values['ages_project_id'] = bill.project_id.id
            if not values.get('ages_analytic_account_id') and bill.analytic_account_id:
                values['ages_analytic_account_id'] = bill.analytic_account_id.id
        if len(mobilizations) == 1:
            values['ages_mobilization_advance_id'] = mobilizations.id
            mob = mobilizations
            if not values.get('ages_contract_id') and mob.contract_id:
                values['ages_contract_id'] = mob.contract_id.id
            if not values.get('ages_sub_company_id') and mob.sub_company_id:
                values['ages_sub_company_id'] = mob.sub_company_id.id
            if not values.get('ages_project_id') and mob.project_id:
                values['ages_project_id'] = mob.project_id.id
            if not values.get('ages_analytic_account_id') and mob.analytic_account_id:
                values['ages_analytic_account_id'] = mob.analytic_account_id.id
        if len(retentions) == 1:
            values['ages_retention_recovery_id'] = retentions.id
            ret = retentions
            if not values.get('ages_contract_id') and ret.contract_id:
                values['ages_contract_id'] = ret.contract_id.id
            if not values.get('ages_sub_company_id') and ret.sub_company_id:
                values['ages_sub_company_id'] = ret.sub_company_id.id
            if not values.get('ages_project_id') and ret.project_id:
                values['ages_project_id'] = ret.project_id.id
            if not values.get('ages_analytic_account_id') and ret.analytic_account_id:
                values['ages_analytic_account_id'] = ret.analytic_account_id.id

        return values

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_commands = res.get('line_ids')
        if line_commands:
            line_ids = []
            for command in line_commands:
                if command[0] == 6:
                    line_ids = list(command[2])
                elif command[0] == 4:
                    line_ids.append(command[1])
            if line_ids:
                lines = self._ages_payment_lines_without_retention(
                    self.env['account.move.line'].browse(line_ids)
                )
                if lines:
                    res['line_ids'] = [Command.set(lines.ids)]
        move_ids = self.env.context.get('active_ids') or []
        moves = self.env['account.move']
        if self.env.context.get('active_model') == 'account.move' and move_ids:
            moves = self.env['account.move'].browse(move_ids).exists()
        elif self.env.context.get('active_model') == 'account.move.line' and move_ids:
            moves = self.env['account.move.line'].browse(move_ids).exists().mapped('move_id')
        values = self._ages_values_from_moves(moves)
        for key, value in values.items():
            if key in fields_list or not fields_list:
                res[key] = value
            else:
                # Still set so form inherits get the value even if field list is partial
                res[key] = value
        if not fields_list or 'journal_id' in fields_list:
            res['journal_id'] = False
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            line_commands = vals.get('line_ids')
            if not line_commands:
                continue
            line_ids = []
            for command in line_commands:
                if command[0] == 6:
                    line_ids = list(command[2])
                elif command[0] == 4:
                    line_ids.append(command[1])
            if not line_ids:
                continue
            lines = self._ages_payment_lines_without_retention(
                self.env['account.move.line'].browse(line_ids)
            )
            if lines:
                vals['line_ids'] = [Command.set(lines.ids)]
        records = super().create(vals_list)
        for wizard, vals in zip(records, vals_list):
            wizard._ages_fill_missing_from_moves()
            # Respect the user turning withholding off or deleting the lines.
            if vals.get('should_withhold_tax') is False:
                wizard.should_withhold_tax = False
                wizard.withholding_line_ids = [Command.clear()]
        return records

    def _ages_fill_missing_from_moves(self):
        """Fill empty AGES fields from linked invoices after wizard create."""
        for wizard in self:
            moves = wizard._ages_get_source_moves()
            values = self._ages_values_from_moves(moves)
            write_vals = {}
            for field_name, value in values.items():
                if not wizard[field_name] and value:
                    write_vals[field_name] = value
            if write_vals:
                wizard.write(write_vals)
                if write_vals.get('ages_running_bill_id') and not wizard.custom_user_amount:
                    wizard._compute_amount()
                    wizard._compute_withholding_line_ids()

    @api.onchange('line_ids')
    def _onchange_line_ids_ages_dimensions(self):
        values = self._ages_values_from_moves(self.line_ids.move_id)
        for field_name, value in values.items():
            if not self[field_name] and value:
                self[field_name] = value

    def _ages_sub_company_from_project(self, project):
        """Active Company the project was opened on, if set."""
        if not project:
            return self.env['ages.sub.company']
        project = project.sudo()
        if 'ages_sub_company_id' in project._fields and project.ages_sub_company_id:
            return project.ages_sub_company_id
        contract = project.ages_contract_id if 'ages_contract_id' in project._fields else False
        if contract and contract.sub_company_id:
            return contract.sub_company_id
        return self.env['ages.sub.company']

    def _ages_project_belongs_to_sub_company(self, project, sub_company):
        if not project or not sub_company:
            return True
        project = project.sudo()
        if 'ages_sub_company_id' in project._fields and project.ages_sub_company_id:
            return project.ages_sub_company_id == sub_company
        contract = project.ages_contract_id if 'ages_contract_id' in project._fields else False
        if contract and contract.sub_company_id:
            return contract.sub_company_id == sub_company
        return True

    @api.onchange('should_withhold_tax')
    def _onchange_should_withhold_tax_ages(self):
        """If the user turns withholding off, keep it off — do not refill on save."""
        if not self.should_withhold_tax:
            self.withholding_line_ids = [Command.clear()]
            self.ages_wht_autofill_done = True

    @api.onchange('ages_sub_company_id')
    def _onchange_ages_sub_company_id(self):
        domain = []
        if self.company_id:
            domain.append(('company_id', 'in', [self.company_id.id, False]))
        if self.ages_sub_company_id:
            domain.append(('ages_contract_id.sub_company_id', '=', self.ages_sub_company_id.id))
        if (
            self.ages_project_id
            and self.ages_sub_company_id
            and not self._ages_project_belongs_to_sub_company(
                self.ages_project_id, self.ages_sub_company_id
            )
        ):
            self.ages_project_id = False
            self.ages_analytic_account_id = False
        return {'domain': {'ages_project_id': domain}}

    @api.onchange('ages_contract_id')
    def _onchange_ages_contract_id(self):
        if self.ages_contract_id:
            contract = self.ages_contract_id
            if contract.project_id:
                self.ages_project_id = contract.project_id
            if contract.analytic_account_id:
                self.ages_analytic_account_id = contract.analytic_account_id
            elif contract.project_id.account_id:
                self.ages_analytic_account_id = contract.project_id.account_id
            if contract.sub_company_id:
                self.ages_sub_company_id = contract.sub_company_id

    @api.onchange('ages_project_id')
    def _onchange_ages_project_id(self):
        if self.ages_project_id:
            self.ages_analytic_account_id = self.ages_project_id.account_id
            contract = self.ages_contract_id
            if contract and contract.project_id and contract.project_id != self.ages_project_id:
                self.ages_contract_id = False
                contract = self.env['ages.contract']
            if not contract:
                contract = self.ages_project_id.ages_contract_id
                if contract:
                    self.ages_contract_id = contract
            sub_company = self._ages_sub_company_from_project(self.ages_project_id)
            if sub_company:
                self.ages_sub_company_id = sub_company
            elif contract and contract.sub_company_id:
                self.ages_sub_company_id = contract.sub_company_id
        else:
            self.ages_analytic_account_id = False

    def _ages_get_single_running_bill(self):
        self.ensure_one()
        if self.ages_running_bill_id:
            return self.ages_running_bill_id
        moves = self._ages_get_source_moves()
        bills = moves.mapped('ages_running_bill_id')
        return bills[:1] if len(bills) == 1 else self.env['ages.running.bill']

    def _ages_get_single_mobilization(self):
        self.ensure_one()
        if self.ages_mobilization_advance_id:
            return self.ages_mobilization_advance_id
        moves = self._ages_get_source_moves()
        records = moves.mapped('ages_mobilization_advance_id')
        return records[:1] if len(records) == 1 else self.env['ages.mobilization.advance']

    def _ages_get_single_retention(self):
        self.ensure_one()
        if self.ages_retention_recovery_id:
            return self.ages_retention_recovery_id
        moves = self._ages_get_source_moves()
        records = moves.mapped('ages_retention_recovery_id')
        return records[:1] if len(records) == 1 else self.env['ages.retention.recovery']

    def _ages_prepare_withholding_command(self, tax, base_amount, tax_amount=0.0):
        """Build a withholding line create command for a tax / base / amount."""
        self.ensure_one()
        if not tax:
            return False
        base_amount = abs(base_amount or 0.0)
        tax_amount = abs(tax_amount or 0.0)
        if not tax_amount and base_amount and tax.amount_type != 'fixed':
            tax_amount = abs(base_amount * (tax.amount or 0.0) / 100.0)
        elif not tax_amount and tax.amount_type == 'fixed':
            tax_amount = abs(tax.amount or 0.0)
        if not tax_amount:
            return False

        currency = self.currency_id or self.company_id.currency_id
        account = (
            self.env['account.withholding.line']._ages_account_from_tax(tax)
            or self.company_id.withholding_tax_base_account_id
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
        return Command.create(vals)

    def _ages_resolve_payment_withholding_tax(self, tax):
        """Use the tax if it is a payment WHT; otherwise match by company/amount."""
        if not tax:
            return tax
        if tax.is_withholding_tax_on_payment:
            return tax
        match = self.env['account.tax'].search([
            *self.env['account.tax']._check_company_domain(tax.company_id or self.company_id),
            ('is_withholding_tax_on_payment', '=', True),
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', tax.amount),
            ('active', '=', True),
        ], limit=1)
        return match or tax

    def _ages_wht_rate(self, tax):
        """Absolute percent rate, e.g. 7.5 → 0.075. Fixed taxes return 0."""
        if not tax or tax.amount_type == 'fixed':
            return 0.0
        return abs(tax.amount or 0.0) / 100.0

    def _ages_wht_amount_from_tax(self, tax, base_amount, currency=None):
        """Withholding amount for a tax on a positive base."""
        currency = currency or self.currency_id or self.company_id.currency_id
        base_amount = abs(base_amount or 0.0)
        if not tax or not base_amount:
            return 0.0
        if tax.amount_type == 'fixed':
            tax_amount = abs(tax.amount or 0.0)
        else:
            tax_amount = abs(base_amount * (tax.amount or 0.0) / 100.0)
        return currency.round(tax_amount) if currency else tax_amount

    def _ages_bill_wht_tax(self, bill=None):
        """WTH % from the running bill, else the contract."""
        bill = bill or self._ages_get_single_running_bill()
        if not bill:
            return self.env['account.tax']
        return bill.wth_tax_id or bill.contract_id.wth_tax_id

    def _ages_bill_sales_wht_tax(self, bill=None):
        """WTH on Sales Tax from the running bill, else the contract."""
        bill = bill or self._ages_get_single_running_bill()
        if not bill:
            return self.env['account.tax']
        tax = bill.wth_on_sales_tax_id or bill.contract_id.wth_on_sales_tax_id
        return self._ages_resolve_payment_withholding_tax(tax)

    def _ages_bill_wht_amount(self, bill):
        amount = abs(bill.wth_amount or 0.0)
        if amount:
            return amount
        tax = self._ages_bill_wht_tax(bill)
        if not tax:
            return 0.0
        currency = self.currency_id or self.company_id.currency_id
        return self._ages_wht_amount_from_tax(tax, bill._get_wht_payment_base(), currency)

    def _ages_bill_sales_wht_amount(self, bill):
        amount = abs(bill.wth_on_sales_tax_amount or 0.0)
        if amount:
            return amount
        tax = self._ages_bill_sales_wht_tax(bill)
        if not tax:
            return 0.0
        currency = self.currency_id or self.company_id.currency_id
        return self._ages_wht_amount_from_tax(tax, bill.sales_tax_amount, currency)

    def _ages_payment_received_net(self, payment):
        taxes = sum(abs(line.amount or 0.0) for line in payment.withholding_line_ids)
        return max(abs(payment.amount or 0.0) - taxes, 0.0)

    def _ages_running_bill_paid_net(self):
        """Bank amounts already received on this running-bill invoice."""
        self.ensure_one()
        moves = self._ages_get_source_moves()
        bill = self._ages_get_single_running_bill()
        if not moves or not bill:
            return 0.0
        move = moves.filtered(lambda rec: rec.ages_running_bill_id == bill)[:1] or moves[:1]
        payments = move._ages_get_posted_running_bill_payments()
        return sum(self._ages_payment_received_net(payment) for payment in payments)

    def _ages_remaining_receive(self, bill):
        """Amount still to receive (running-bill net minus posted bank)."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        full = abs(bill.net_amount or 0.0)
        remaining = max(full - self._ages_running_bill_paid_net(), 0.0)
        return currency.round(remaining)

    def _ages_gross_up_bank(self, bank, tax, currency=None):
        """Turn the bank amount into payment Amount: bank / (100 − rate) × 100.

        7.5% → bank / 92.5 × 100. 8% → bank / 92 × 100.
        """
        currency = currency or self.currency_id or self.company_id.currency_id
        bank = abs(bank or 0.0)
        if tax and tax.amount_type == 'fixed':
            gross = bank + abs(tax.amount or 0.0)
        else:
            rate = self._ages_wht_rate(tax)
            if 0.0 < rate < 1.0:
                gross = bank / (1.0 - rate)
            else:
                gross = bank
        return currency.round(gross) if currency else gross

    def _ages_taxes_for_receive(self, bill, receive):
        """Gross-up the bank amount; WTH % sits on that gross so Net stays the bank."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        receive = currency.round(abs(receive or 0.0))
        tax = self._ages_bill_wht_tax(bill)
        gross = self._ages_gross_up_bank(receive, tax, currency)
        wht_amount = self._ages_wht_amount_from_tax(tax, gross, currency) if tax else 0.0
        return receive, gross, wht_amount

    def _ages_gross_for_receive(self, bill, receive):
        """Amount = bank / (100 − WTH %) × 100."""
        _receive, gross, _wht = self._ages_taxes_for_receive(bill, receive)
        return gross

    def _ages_receive_from_gross(self, bill, amount):
        """Invert Amount back to the bank figure: Amount × (100 − rate) / 100."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        amount = abs(amount or 0.0)
        if not amount:
            return 0.0
        tax = self._ages_bill_wht_tax(bill)
        if tax and tax.amount_type == 'fixed':
            return currency.round(max(amount - abs(tax.amount or 0.0), 0.0))
        rate = self._ages_wht_rate(tax) if tax else 0.0
        if 0.0 < rate < 1.0:
            return currency.round(amount * (1.0 - rate))
        return currency.round(amount)

    def _ages_current_receive_guess(self, bill):
        tax = self._ages_bill_wht_tax(bill)
        if tax:
            line = self.withholding_line_ids.filtered(lambda rec: rec.tax_id == tax)[:1]
            if line and line.base_amount:
                return self._ages_receive_from_gross(bill, line.base_amount)
        # Do NOT fall back to full net_amount when remaining is 0 — that re-applies
        # income WTH after the bill net was already paid (causes 2× WTH / 694k error).
        return self._ages_remaining_receive(bill)

    def _ages_invoice_amount_for_difference(self):
        """Invoice residual Odoo uses for Payment Difference."""
        self.ensure_one()
        if not self.payment_date or not self.can_edit_wizard:
            return abs(self.source_amount_currency or self.source_amount or 0.0)
        totals = self._get_total_amounts_to_pay(self.batches)
        if self.installments_mode == 'full':
            return totals.get('full_amount_for_difference') or 0.0
        return totals.get('amount_for_difference') or 0.0

    def _ages_absorb_residual_rounding(self):
        """Snap Amount and WHT base when they are one rounding unit off residual.

        7.5% gross-up can land 0.01 over the invoice, which shows Payment
        Difference -0.01. Pull Amount back to residual so the bill can close.
        """
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        residual = self._ages_invoice_amount_for_difference()
        amount = abs(self.amount or 0.0)
        if not residual or not amount:
            return False
        rounding = currency.rounding or 0.01
        if abs(residual - amount) > rounding + 1e-9:
            return False
        if not currency.compare_amounts(amount, residual):
            return False
        snapped = currency.round(residual)
        self.amount = snapped
        if self.custom_user_amount:
            self.custom_user_amount = snapped
            self.custom_user_currency_id = currency
        tax = self._ages_running_bill_payment_tax()
        if tax:
            wht = self._ages_wht_amount_from_tax(tax, snapped, currency)
            self._ages_set_withholding_line_values(tax, snapped, wht)
        return True

    def _ages_running_bill_default_payment_amount(self):
        """Default Amount = remaining bank grossed up by the contract WTH %."""
        self.ensure_one()
        bill = self._ages_get_single_running_bill()
        if not bill:
            return 0.0
        if not self._ages_bill_wht_tax(bill):
            return 0.0
        receive = self._ages_remaining_receive(bill)
        if not receive:
            return 0.0
        gross = self._ages_gross_for_receive(bill, receive)
        residual = self._ages_invoice_amount_for_difference()
        currency = self.currency_id or self.company_id.currency_id
        rounding = currency.rounding or 0.01
        if residual and abs(residual - gross) <= rounding + 1e-9:
            return currency.round(residual)
        return gross

    def _ages_sales_tax_wht_taxes(self, bill):
        """WTH on Sales Tax from the running bill / contract only."""
        taxes = self.env['account.tax']
        if not bill:
            return taxes
        raw = bill.wth_on_sales_tax_id or bill.contract_id.wth_on_sales_tax_id
        if raw:
            taxes |= raw
        resolved = self._ages_bill_sales_wht_tax(bill)
        if resolved:
            taxes |= resolved
        return taxes

    def _ages_is_sales_tax_wht_line(self, line, bill=None):
        """True when the line is the contract/bill WTH on Sales Tax."""
        if not line or not line.tax_id:
            return False
        return line.tax_id in self._ages_sales_tax_wht_taxes(bill)

    def _ages_running_bill_keep_taxes(self, bill=None):
        """Only the withholding taxes set on the running bill / contract."""
        self.ensure_one()
        bill = bill or self._ages_get_single_running_bill()
        taxes = self.env['account.tax']
        wht = self._ages_bill_wht_tax(bill)
        if wht:
            taxes |= wht
        return taxes

    def _ages_drop_other_withholding_lines(self, bill=None):
        """Keep contract/bill withholding taxes; drop anything else."""
        for wizard in self:
            src = bill or wizard._ages_get_single_running_bill()
            if not src:
                continue
            keep = wizard._ages_running_bill_keep_taxes(src)
            drop = wizard.withholding_line_ids.filtered(
                lambda line: line.tax_id and line.tax_id not in keep
            )
            if drop:
                wizard.withholding_line_ids = wizard.withholding_line_ids - drop

    def _ages_running_bill_payment_tax(self, bill=None):
        """WTH % from the running bill / contract."""
        self.ensure_one()
        return self._ages_bill_wht_tax(bill)

    def _ages_sales_tax_wht_tax(self, bill=None):
        self.ensure_one()
        return self._ages_bill_sales_wht_tax(bill)

    def _ages_running_bill_remaining_srb(self, bill=None):
        self.ensure_one()
        bill = bill or self._ages_get_single_running_bill()
        currency = self.currency_id or self.company_id.currency_id
        full = self._ages_bill_sales_wht_amount(bill) if bill else 0.0
        if not full:
            return 0.0
        taxes = self._ages_sales_tax_wht_taxes(bill)
        posted = 0.0
        moves = self._ages_get_source_moves()
        move = moves.filtered(lambda rec: rec.ages_running_bill_id == bill)[:1] or moves[:1]
        if move and taxes:
            posted = move._ages_sum_posted_withholding(
                move._ages_get_posted_running_bill_payments(),
                taxes,
            )
        return currency.round(max(full - posted, 0.0))

    def _ages_running_bill_remaining_wht(self, bill=None):
        """Income WTH still allowed on this bill (bill WTH Amount minus prior payments)."""
        self.ensure_one()
        bill = bill or self._ages_get_single_running_bill()
        if not bill:
            return 0.0
        currency = self.currency_id or self.company_id.currency_id
        full = self._ages_bill_wht_amount(bill)
        if not full:
            return 0.0
        tax = self._ages_bill_wht_tax(bill)
        posted = 0.0
        moves = self._ages_get_source_moves()
        move = moves.filtered(lambda rec: rec.ages_running_bill_id == bill)[:1] or moves[:1]
        if move and tax:
            posted = move._ages_sum_posted_withholding(
                move._ages_get_posted_running_bill_payments(),
                tax,
            )
        return currency.round(max(full - posted, 0.0))

    def _ages_cap_running_bill_wht_amount(self, bill, wht_amount):
        """Never withhold more than the running bill's remaining WTH Amount (Rs)."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        remaining = self._ages_running_bill_remaining_wht(bill)
        capped = min(abs(wht_amount or 0.0), remaining)
        return currency.round(capped)

    def _ages_set_withholding_line_values(self, tax, base, amount):
        self.ensure_one()
        if not tax:
            return
        currency = self.currency_id or self.company_id.currency_id
        base = currency.round(abs(base or 0.0))
        amount = currency.round(abs(amount or 0.0))
        lines = self.withholding_line_ids.filtered(lambda rec: rec.tax_id == tax)
        # Cap / remaining WHT may be 0 — remove the line instead of leaving a stale amount.
        if currency.is_zero(amount):
            if lines:
                self.withholding_line_ids = self.withholding_line_ids - lines
            return
        line = lines[:1]
        extras = lines[1:]
        if extras:
            self.withholding_line_ids = self.withholding_line_ids - extras
        if line:
            line.base_amount = base
            line.source_base_amount_currency = base
            line.source_base_amount = base
            if 'original_base_amount' in line._fields:
                line.original_base_amount = base
            line.amount = amount
            line.source_tax_amount_currency = amount
            line.source_tax_amount = amount
            if 'original_tax_amount' in line._fields:
                line.original_tax_amount = amount
            return
        self._ages_append_withholding_command(
            self._ages_prepare_withholding_command(tax, base, amount)
        )

    def _ages_apply_typed_running_bill_amount(self):
        """Typed Amount is the bank figure; replace it with bank / (100 − WTH %) × 100."""
        self.ensure_one()
        bill = self._ages_get_single_running_bill()
        if not bill or not self.can_edit_wizard:
            return
        tax = self._ages_running_bill_payment_tax(bill)
        if not tax:
            self._ages_drop_other_withholding_lines(bill)
            return
        currency = self.currency_id or self.company_id.currency_id
        typed = abs(self.amount or 0.0)
        if not typed:
            return
        suggested = self._ages_running_bill_default_payment_amount()
        if suggested and not currency.compare_amounts(typed, suggested):
            self.custom_user_amount = None
            self.custom_user_currency_id = None
            self._ages_sync_running_bill_withholding_to_amount(
                self._ages_remaining_receive(bill)
            )
            self._ages_absorb_residual_rounding()
            return
        guess = self._ages_current_receive_guess(bill)
        expected_gross = self._ages_gross_for_receive(bill, guess) if guess else 0.0
        if guess and expected_gross and not currency.compare_amounts(typed, expected_gross):
            self._ages_sync_running_bill_withholding_to_amount(guess)
            self._ages_absorb_residual_rounding()
            return
        residual = self._ages_invoice_amount_for_difference()
        rounding = currency.rounding or 0.01
        if residual and abs(typed - residual) <= rounding + 1e-9:
            self.amount = currency.round(residual)
            tax = self._ages_running_bill_payment_tax(bill)
            if tax:
                wht = self._ages_wht_amount_from_tax(tax, self.amount, currency)
                wht = self._ages_cap_running_bill_wht_amount(bill, wht)
                self._ages_set_withholding_line_values(tax, self.amount, wht)
            return
        gross = self._ages_gross_for_receive(bill, typed)
        if currency.compare_amounts(gross, typed):
            self.amount = gross
            self.custom_user_amount = gross
            self.custom_user_currency_id = currency
        self._ages_sync_running_bill_withholding_to_amount(typed)
        self._ages_absorb_residual_rounding()

    def _ages_sync_running_bill_withholding_if_default_amount(self):
        """Compute-time sync only when Amount is already the running-bill gross.

        If the user just typed a debit, Amount is not the gross yet. Syncing here
        would copy that debit onto the WHT line and block the debit→gross onchange.
        """
        self.ensure_one()
        bill = self._ages_get_single_running_bill()
        if not bill:
            return
        currency = self.currency_id or self.company_id.currency_id
        suggested = self._ages_running_bill_default_payment_amount()
        if suggested and not currency.compare_amounts(self.amount or 0.0, suggested):
            self._ages_sync_running_bill_withholding_to_amount(
                self._ages_remaining_receive(bill)
            )

    def _ages_sync_running_bill_withholding_to_amount(self, receive=None):
        """WTH base = grossed-up Amount. WTH on Sales Tax is not a payment line."""
        self.ensure_one()
        bill = self._ages_get_single_running_bill()
        if (
            not bill
            or not self.display_withholding
            or not self.can_edit_wizard
        ):
            return
        if self.should_withhold_tax is False and self.ages_wht_autofill_done:
            return
        tax = self._ages_running_bill_payment_tax(bill)
        if not tax:
            self._ages_drop_other_withholding_lines(bill)
            return
        currency = self.currency_id or self.company_id.currency_id
        if receive is None:
            amount = currency.round(abs(self.amount or 0.0))
            if not amount:
                return
            guess = self._ages_current_receive_guess(bill)
            if guess and not currency.compare_amounts(
                amount, self._ages_gross_for_receive(bill, guess)
            ):
                receive = guess
            else:
                receive = self._ages_receive_from_gross(bill, amount)
        _receive, gross, wht_amount = self._ages_taxes_for_receive(bill, receive)
        if tax and wht_amount:
            wht_amount = self._ages_cap_running_bill_wht_amount(bill, wht_amount)
            self._ages_set_withholding_line_values(tax, gross, wht_amount)
        self._ages_drop_other_withholding_lines(bill)
        if self.withholding_line_ids:
            self.should_withhold_tax = True

    def _ages_prepare_running_bill_withholding_command(self, bill):
        """Contract/bill WTH % line; base is the amount still to receive (bank)."""
        self.ensure_one()
        tax = self._ages_bill_wht_tax(bill)
        if not tax:
            return False
        receive = self._ages_remaining_receive(bill)
        if not receive:
            return False
        _recv, gross, wht_amount = self._ages_taxes_for_receive(bill, receive)
        wht_amount = self._ages_cap_running_bill_wht_amount(bill, wht_amount)
        if not wht_amount:
            return False
        return self._ages_prepare_withholding_command(tax, gross, wht_amount)

    def _ages_append_withholding_command(self, command):
        self.ensure_one()
        if not command:
            return
        commands = [Command.clear()]
        for line in self.withholding_line_ids:
            data = line.copy_data()[0]
            data.pop('payment_register_id', None)
            commands.append(Command.create(data))
        commands.append(command)
        self.withholding_line_ids = commands

    def _ages_has_source_document(self):
        self.ensure_one()
        return bool(
            self._ages_get_single_running_bill()
            or self._ages_get_single_mobilization()
            or self._ages_get_single_retention()
        )

    def _ages_apply_running_bill_withholding(self):
        """Prefill WHT once from Running Bill, Mobilization Advance, or Retention."""
        for wizard in self:
            if wizard.ages_wht_autofill_done:
                continue
            if not wizard.display_withholding or not wizard.can_edit_wizard:
                continue

            wizard.ages_wht_autofill_done = True
            bill = wizard._ages_get_single_running_bill()
            if bill:
                wizard._ages_drop_other_withholding_lines(bill)
                wht_tax = wizard._ages_bill_wht_tax(bill)
                if wht_tax and not wizard.withholding_line_ids.filtered(
                    lambda line: line.tax_id == wht_tax
                ):
                    wizard._ages_append_withholding_command(
                        wizard._ages_prepare_running_bill_withholding_command(bill)
                    )
                if wht_tax:
                    wizard._ages_sync_running_bill_withholding_if_default_amount()
                    continue

            mob = wizard._ages_get_single_mobilization()
            if mob and mob.wht_on_mobilization and mob.wth_tax_id:
                if not wizard.withholding_line_ids.filtered(lambda line: line.tax_id == mob.wth_tax_id):
                    wizard._ages_append_withholding_command(
                        wizard._ages_prepare_withholding_command(
                            mob.wth_tax_id,
                            mob.mobilization_amount,
                            mob.wth_amount,
                        )
                    )
                continue

            ret = wizard._ages_get_single_retention()
            if ret and ret.wht_on_retention and ret.wth_tax_id:
                if not wizard.withholding_line_ids.filtered(lambda line: line.tax_id == ret.wth_tax_id):
                    wizard._ages_append_withholding_command(
                        wizard._ages_prepare_withholding_command(
                            ret.wth_tax_id,
                            ret.retention_amount,
                            ret.wth_amount,
                        )
                    )

    @api.depends(
        'can_edit_wizard',
        'display_withholding',
        'ages_running_bill_id',
        'ages_running_bill_id.wth_tax_id',
        'ages_running_bill_id.wth_amount',
        'ages_running_bill_id.ex_rebate_mr_value',
        'ages_running_bill_id.mobilization_amount',
        'ages_running_bill_id.retention_amount',
        'ages_running_bill_id.wht_on_mobilization',
        'ages_running_bill_id.wht_on_retention',
        'ages_running_bill_id.wth_on_sales_tax_id',
        'ages_running_bill_id.wth_on_sales_tax_amount',
        'ages_running_bill_id.sales_tax_amount',
        'ages_running_bill_id.contract_id.wth_tax_id',
        'ages_running_bill_id.contract_id.wth_on_sales_tax_id',
        'ages_mobilization_advance_id',
        'ages_mobilization_advance_id.wth_tax_id',
        'ages_mobilization_advance_id.wth_amount',
        'ages_mobilization_advance_id.mobilization_amount',
        'ages_mobilization_advance_id.wht_on_mobilization',
        'ages_retention_recovery_id',
        'ages_retention_recovery_id.wth_tax_id',
        'ages_retention_recovery_id.wth_amount',
        'ages_retention_recovery_id.retention_amount',
        'ages_retention_recovery_id.wht_on_retention',
        'line_ids',
        'line_ids.move_id.ages_running_bill_id',
        'line_ids.move_id.ages_mobilization_advance_id',
        'line_ids.move_id.ages_retention_recovery_id',
    )
    def _compute_withholding_line_ids(self):
        """Prefill WTH from Running Bill or Mobilization Advance."""
        super()._compute_withholding_line_ids()
        self._ages_drop_other_withholding_lines()
        self._ages_apply_running_bill_withholding()
        for wizard in self:
            wizard._ages_sync_running_bill_withholding_if_default_amount()

    @api.depends(
        'can_edit_wizard',
        'source_amount',
        'source_amount_currency',
        'source_currency_id',
        'company_id',
        'currency_id',
        'payment_date',
        'installments_mode',
        'ages_running_bill_id',
        'ages_running_bill_id.net_amount',
        'ages_running_bill_id.wth_amount',
        'ages_running_bill_id.wth_on_sales_tax_amount',
        'ages_running_bill_id.contract_id.wth_tax_id',
        'ages_running_bill_id.contract_id.wth_on_sales_tax_id',
    )
    def _compute_amount(self):
        """Running-bill Pay defaults to receive + WTH%(receive) + WTH on Sales Tax."""
        super()._compute_amount()
        for wizard in self:
            if wizard.custom_user_amount:
                continue
            bill = wizard._ages_get_single_running_bill()
            if bill:
                receive = wizard._ages_remaining_receive(bill)
                if receive:
                    wizard.ages_actual_amount = receive
            suggested = wizard._ages_running_bill_default_payment_amount()
            if suggested:
                wizard.amount = suggested
                wizard._ages_absorb_residual_rounding()

    def _ages_apply_actual_amount(self, receive=None):
        """Actual Amount is the bank figure; Amount and WHT follow it."""
        self.ensure_one()
        bill = self._ages_get_single_running_bill()
        if not bill or not self.can_edit_wizard:
            return
        currency = self.currency_id or self.company_id.currency_id
        receive = currency.round(abs(
            receive if receive is not None else self.ages_actual_amount or 0.0
        ))
        self.ages_actual_amount = receive
        if not receive:
            return
        tax = self._ages_running_bill_payment_tax(bill)
        if not tax:
            self.amount = receive
            return
        gross = self._ages_gross_for_receive(bill, receive)
        self.amount = gross
        self.custom_user_amount = gross
        self.custom_user_currency_id = currency
        self._ages_sync_running_bill_withholding_to_amount(receive)
        self._ages_absorb_residual_rounding()

    @api.onchange('ages_actual_amount')
    def _onchange_ages_actual_amount(self):
        """Typed Actual Amount is the bank figure; Amount gets the tax added."""
        if self._ages_get_single_running_bill():
            self._ages_apply_actual_amount()

    @api.onchange('amount')
    def _onchange_amount(self):
        """Typed running-bill Amount is the receive figure; add contract/bill taxes."""
        res = super()._onchange_amount()
        if self._ages_get_single_running_bill():
            self._ages_apply_typed_running_bill_amount()
        return res

    def _ages_payment_dimension_vals(self, batch_result=None):
        self.ensure_one()
        values = {
            'ages_sub_company_id': self.ages_sub_company_id.id,
            'ages_contract_id': self.ages_contract_id.id,
            'ages_project_id': self.ages_project_id.id,
            'ages_analytic_account_id': self.ages_analytic_account_id.id,
            'ages_running_bill_id': self.ages_running_bill_id.id,
            'ages_mobilization_advance_id': self.ages_mobilization_advance_id.id,
            'ages_retention_recovery_id': self.ages_retention_recovery_id.id,
        }
        if not any(values.values()) and batch_result:
            moves = batch_result['lines'].move_id
            values = self._ages_values_from_moves(moves)
        return values

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        payment_vals.update(self._ages_payment_dimension_vals(batch_result))
        if not self.should_withhold_tax:
            payment_vals['should_withhold_tax'] = False
            payment_vals['withholding_line_ids'] = []
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        payment_vals.update(self._ages_payment_dimension_vals(batch_result))
        return payment_vals

    def _ages_wizard_wht_amount_for_taxes(self, taxes):
        """Sum current wizard withholding amounts that match the given taxes."""
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

    def _ages_force_cap_running_bill_withholding(self):
        """Re-apply remaining-WTH cap right before create (dedupe + trim)."""
        self.ensure_one()
        bill = self._ages_get_single_running_bill()
        if not bill:
            return
        tax = self._ages_bill_wht_tax(bill)
        if not tax:
            return
        line = self.withholding_line_ids.filtered(lambda rec: rec.tax_id == tax)[:1]
        if not line:
            return
        remaining = self._ages_running_bill_remaining_wht(bill)
        capped = self._ages_cap_running_bill_wht_amount(bill, line.amount)
        self._ages_set_withholding_line_values(tax, line.base_amount, capped)
        if not remaining and self.should_withhold_tax and not self.withholding_line_ids:
            self.should_withhold_tax = False

    def _ages_check_withholding_against_invoice(self):
        """Block recording more WTH than the running bill actual amounts."""
        self.ensure_one()
        self._ages_force_cap_running_bill_withholding()
        if not self.should_withhold_tax:
            return
        bill = self._ages_get_single_running_bill()
        if not bill:
            return
        moves = self._ages_get_source_moves()
        move = moves.filtered(lambda rec: rec.ages_running_bill_id == bill)[:1] or moves[:1]
        posted = move._ages_get_posted_running_bill_payments() if move else self.env['account.payment']
        currency = self.currency_id or self.company_id.currency_id
        rounding = currency.rounding or 0.01

        wht_tax = self._ages_bill_wht_tax(bill)
        checks = [(
            wht_tax,
            self._ages_bill_wht_amount(bill),
            self.env._('WTH Amount (Rs)'),
        )]
        for taxes, actual, label in checks:
            if not taxes:
                continue
            posted_amount = (
                move._ages_sum_posted_withholding(posted, taxes) if move else 0.0
            )
            current = self._ages_wizard_wht_amount_for_taxes(taxes)
            recorded = posted_amount + current
            if float_compare(recorded, actual, precision_rounding=rounding) > 0:
                raise UserError(self.env._(
                    'Recorded %(label)s (%(recorded)s) cannot exceed the bill amount '
                    '(%(actual)s).\n'
                    'Already on payments for this Running Bill: %(posted)s\n'
                    'On this Pay wizard: %(current)s\n'
                    'Reduce withholding (or cancel the earlier payment that already '
                    'took WTH on RA-Bill %(bill)s).',
                    label=label,
                    recorded=currency.format(recorded),
                    actual=currency.format(actual),
                    posted=currency.format(posted_amount),
                    current=currency.format(current),
                    bill=bill.display_name,
                ))

    @api.depends('available_journal_ids')
    def _compute_journal_id(self):
        """Do not auto-select a journal. The user must choose one."""
        for wizard in self:
            if wizard.journal_id and wizard.journal_id in wizard.available_journal_ids:
                wizard.journal_id = wizard.journal_id
            else:
                wizard.journal_id = False

    def action_create_payments(self):
        for wizard in self:
            if not wizard.journal_id:
                raise UserError(self.env._('Journal is required to create the payment.'))
            if not wizard.ages_sub_company_id:
                raise UserError(self.env._('Active Company is required to create the payment.'))
            wizard._ages_force_cap_running_bill_withholding()
            wizard._ages_check_withholding_against_invoice()
        return super().action_create_payments()

    def _create_payments(self):
        for wizard in self:
            payable_lines = wizard._ages_payment_lines_without_retention(wizard.line_ids)
            if payable_lines and payable_lines != wizard.line_ids:
                wizard.line_ids = payable_lines
        payments = super()._create_payments()
        payments._ages_sync_linked_documents_from_reconciled()
        return payments

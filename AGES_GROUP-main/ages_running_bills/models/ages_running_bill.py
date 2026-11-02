# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError

from odoo.addons.ages_project_configs.models.res_company import AMOUNT_BASE_SELECTION


class AgesRunningBill(models.Model):
    _name = 'ages.running.bill'
    _inherit = ['ages.running.bill', 'mail.thread', 'mail.activity.mixin']
    _description = 'Running Bill'
    _order = 'id desc'

    name = fields.Char(
        string='Running Bill Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('state', '=', 'running'), ('partner_id', '=', partner_id)]",
    )
    project_wise_contract = fields.Char(
        related='contract_id.project_wise_name',
        string='Project-Wise Contract',
        readonly=True,
        help='Contract name as used on this project (Contract 1, Contract 2, …).',
    )
    contract_description = fields.Text(
        related='contract_id.contract_description',
        string='Contract Description',
        readonly=True,
        help='Short description copied from the contract (e.g. BMR 1).',
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        required=True,
        tracking=True,
        domain="[('partner_id', '=', partner_id)]",
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        compute='_compute_analytic_account_id',
        store=True,
        readonly=True,
        help='Project analytic used on the invoice and journal items.\n'
             'Formula: taken from the selected Project.',
    )
    sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        compute='_compute_sub_company_id',
        store=True,
        readonly=True,
        help='Active Company for this bill. Controls which Sales Tax / WTH taxes you can pick.\n'
             'Formula: taken from the Contract.',
    )
    allowed_sales_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        related='sub_company_id.sales_tax_ids',
        string='Allowed Sales Taxes',
    )
    allowed_wth_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        related='sub_company_id.wth_tax_ids',
        string='Allowed WTH Taxes',
    )
    allowed_wth_on_sales_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        related='sub_company_id.wth_on_sales_tax_ids',
        string='Allowed WTH on Sales Tax',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    # ---- Amounts (A..I / Net) ----
    value_of_work_done = fields.Monetary(
        string='Value of Work Done (Rs)',
        currency_field='currency_id',
        required=True,
        default=0.0,
        tracking=True,
        help='Work completed on this running bill only (A). The figure after / is the full contract value.\n'
             'Formula: type this bill’s work done. Display = This Bill / Contract Total.',
    )
    contract_total_work_done = fields.Integer(
        related='contract_id.total_work_done_value',
        string='Contract Total Work Done',
        readonly=True,
        help='Full contract value. Shown after / next to Value of Work Done so you can see how much of the contract this bill covers.\n'
             'Formula: Contract → Total Contract Value.',
    )
    value_of_work_done_display = fields.Char(
        string='Value of Work Done (Rs)',
        compute='_compute_value_of_work_done_display',
        help='This bill’s work done compared with the full contract.\n'
             'Formula: This Bill / Contract Total.',
    )
    rebate_percent = fields.Float(
        string='Rebate (%)',
        digits=(16, 3),
        default=0.0,
        help='Discount given on this bill’s work done. Changing the % updates Rebate Amount.\n'
             'Formula: Rebate Amount = Value of Work Done × Rebate % / 100.',
    )
    rebate_amount = fields.Monetary(
        string='Rebate Amount (Rs)',
        compute='_compute_amount_fields',
        inverse='_inverse_rebate_amount',
        store=True,
        readonly=False,
        currency_field='currency_id',
        help='Rupees taken off work done as rebate (B). You can type the amount; Rebate % is then recalculated.\n'
             'Formula: Value of Work Done × Rebate % / 100.',
    )
    ex_rebate_value = fields.Monetary(
        string='Ex Rebate Value (Rs)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Work done after the rebate is removed (C). Used as Amount Base option C.\n'
             'Formula: Value of Work Done − Rebate Amount.',
    )
    material_recovery = fields.Monetary(
        string='Material Recovery',
        compute='_compute_material_recovery',
        store=True,
        currency_field='currency_id',
        help='Value of materials recovered from the client on this bill (D). Comes from the Recovery Material tab.\n'
             'Formula: sum of Recovery Material lines (Quantity × Rate).',
    )
    ex_rebate_mr_value = fields.Monetary(
        string='Ex Rebate & MR Value (Rs)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Work done after rebate and after material recovery (E). This is the Work Done line on the invoice. Also Amount Base option E.\n'
             'Formula: Ex Rebate Value − Material Recovery.',
    )
    sales_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Sales Tax %',
        domain="[('type_tax_use', '=', 'sale'), ('tax_scope', '=', 'service'), "
               "('active', '=', True), ('id', 'in', allowed_sales_tax_ids)]",
        check_company=True,
        help='Provincial sales tax rate (e.g. 15% Sindh SRB). Not income WTH.\n'
             'Formula: selected tax % × Sales Tax Amount Base (see Amount Bases tab).',
    )
    sales_tax_amount = fields.Monetary(
        string='Sales Tax Amount (Rs)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Sales tax on this bill (F). The invoice books 100% on the SRB account as a credit, '
             'then debits the WTH on Sales Tax share (e.g. 20%) on the same account so net SRB = 80%.\n'
             'Formula: Sales Tax % × Sales Tax Amount Base (A = Work Done, C = Ex Rebate, or E = Ex Rebate & MR).',
    )
    total_receivable_ex_sales_tax = fields.Monetary(
        string='Total Receivable(Ex Sales Tax)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='What the client owes on this bill before sales tax. Mobilization and retention have already been deducted.\n'
             'Formula: Ex Rebate & MR − Retention Amount − Mobilization Amount.',
    )
    total_receivable = fields.Monetary(
        string='Total Receivable(Inc Sales Tax)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='What the client owes including full sales tax, before income withholding.\n'
             'Invoice books Work Done + 100% Sales Tax − WTH on Sales Tax − Mob − Ret '
             '(SRB ledger: credit 100%, debit 20%, net 80%).\n'
             'Formula: Ex Rebate & MR − Retention − Mobilization + Sales Tax Amount.',
    )
    mobilization_percent = fields.Float(
        string='Mobilization (%)',
        digits=(16, 2),
        default=0.0,
        help='Share of this bill recovered as mobilization advance (already received earlier).\n'
             'Formula: Mobilization Amount = Mobilization Amount Base × Mobilization % / 100.',
    )
    mobilization_amount = fields.Monetary(
        string='Mobilization Amount (Rs)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Mobilization recovered on this bill (H). Deducted from Total Receivable.\n'
             'Formula: Mobilization Amount Base × Mobilization % / 100.',
    )
    retention_percent = fields.Float(
        string='Retention (%)',
        digits=(16, 2),
        default=0.0,
        help='Share of this bill held as retention (paid later when the contract is closed).\n'
             'Formula: Retention Amount = Retention Amount Base × Retention % / 100.',
    )
    retention_amount = fields.Monetary(
        string='Retention Amount (Rs)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Retention held on this bill (I). Deducted from Total Receivable.\n'
             'Formula: Retention Amount Base × Retention % / 100.',
    )
    wth_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='WTH %',
        domain="[('is_withholding_tax_on_payment', '=', True), ('active', '=', True), "
               "('id', 'in', allowed_wth_tax_ids)]",
        check_company=True,
        help='Income withholding (WH TAX), deducted when the client pays. This is not WTH on Sales Tax (WHSRB).\n'
             'Formula: selected tax % × Total Receivable (Inc Sales Tax).',
    )
    wth_amount = fields.Monetary(
        string='WTH Amount (Rs)',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Income tax the client withholds from payment (WH TAX). Shown as a positive amount.\n'
             'WTH base = Total Receivable (Inc Sales Tax).\n'
             'Formula: |WTH % × Total Receivable (Inc Sales Tax)|.',
    )
    net_amount = fields.Monetary(
        string='Net Amount',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Cash the client should pay after both withholdings. On Pay, type this (or a part of it) in Actual Amount.\n'
             'Formula: Receivable (Inc Sales Tax) − WTH on Sales Tax − WTH Amount.',
    )
    invoice_move_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='ages_running_bill_id',
        string='Invoices',
    )
    invoiced_amount = fields.Monetary(
        string='Invoiced Amount',
        compute='_compute_invoiced_amount',
        currency_field='currency_id',
        help='Total already booked on the customer invoice for this bill. Usually Receivable (Inc Sales Tax) minus WTH on Sales Tax. Not the same as Net Amount (Net also subtracts income WTH).\n'
             'Formula: sum of posted customer invoice totals linked to this bill.',
    )
    # ---- Amount Bases ----
    mobilization_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Mobilization Amount-Base',
        help='Which work-done figure Mobilization % is applied to. Defaults from the contract / project settings.\n'
             'A = Value of Work Done, C = Ex Rebate Value, E = Ex Rebate & MR (usual default).\n'
             'Formula: Mobilization Amount = selected base × Mobilization % / 100.',
    )
    retention_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Retention Amount-Base',
        help='Which work-done figure Retention % is applied to. Defaults from the contract / project settings.\n'
             'A = Value of Work Done, C = Ex Rebate Value, E = Ex Rebate & MR (usual default).\n'
             'Formula: Retention Amount = selected base × Retention % / 100.',
    )
    sales_tax_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Sales Tax Amount Base',
        help='Which work-done figure Sales Tax % is applied to. Used only for Sales Tax Amount — not for income WTH.\n'
             'A = Value of Work Done, C = Ex Rebate Value, E = Ex Rebate & MR (usual default).\n'
             'Formula: Sales Tax Amount = selected base × Sales Tax % / 100.',
    )
    wht_on_mobilization = fields.Boolean(
        string='WHT on Mobilization',
        default=True,
        help='Informational: Total Receivable already deducts Mobilization, and WTH Amount '
             'is computed on Total Receivable (Inc Sales Tax). Does not change Mobilization Amount.',
    )
    wht_on_retention = fields.Boolean(
        string='WHT on Retention',
        default=True,
        help='Informational: Total Receivable already deducts Retention, and WTH Amount '
             'is computed on Total Receivable (Inc Sales Tax). Does not change Retention Amount.',
    )
    wth_on_sales_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='WTH on Sales Tax (%)',
        domain="[('type_tax_use', '=', 'sale'), ('tax_scope', '=', 'service'), "
               "('active', '=', True), ('amount', '<', 0), "
               "('id', 'in', allowed_wth_on_sales_tax_ids)]",
        check_company=True,
        help='Share of sales tax the client withholds (WHSRB, e.g. 20/80). This is not income WTH (WH TAX).\n'
             'Formula: selected tax % × Sales Tax Amount.',
    )
    wth_on_sales_tax_amount = fields.Monetary(
        string='WTH on Sales Tax',
        compute='_compute_amount_fields',
        store=True,
        currency_field='currency_id',
        help='Sales tax the client keeps (WHSRB). Booked on the invoice as a debit on the same '
             'SRB payable account as the 100% sales-tax credit (net SRB = 80%).\n'
             'Formula: |WTH on Sales Tax % × Sales Tax Amount|.',
    )

    # ---- Recovery Material ----
    material_line_ids = fields.One2many(
        comodel_name='ages.running.bill.material.line',
        inverse_name='running_bill_id',
        string='Recovery Material',
        copy=True,
    )

    # ---- Invoice link ----
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        copy=False,
        readonly=True,
    )
    invoice_state = fields.Selection(
        related='invoice_id.state',
        string='Invoice Status',
        store=True,
    )
    invoice_payment_state = fields.Selection(
        related='invoice_id.payment_state',
        string='Payment Status',
        store=True,
        help='Payment status of the customer invoice booked for this bill (Not Paid, Partial, Paid).',
    )
    contract_count = fields.Integer(
        string='Contract Count',
        compute='_compute_contract_count',
    )

    @api.depends('contract_id')
    def _compute_contract_count(self):
        for bill in self:
            bill.contract_count = 1 if bill.contract_id else 0

    # -------------------------------------------------------------------------
    # Defaults / onchange from contract
    # -------------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        if 'mobilization_amount_base' in fields_list and not res.get('mobilization_amount_base'):
            res['mobilization_amount_base'] = company.ages_mobilization_amount_base or 'work_done_ex_rebate_mr'
        if 'retention_amount_base' in fields_list and not res.get('retention_amount_base'):
            res['retention_amount_base'] = company.ages_retention_amount_base or 'work_done_ex_rebate_mr'
        if 'sales_tax_amount_base' in fields_list and not res.get('sales_tax_amount_base'):
            res['sales_tax_amount_base'] = company.ages_sales_tax_amount_base or 'work_done_ex_rebate_mr'
        return res

    @api.depends('project_id', 'project_id.account_id')
    def _compute_analytic_account_id(self):
        for bill in self:
            bill.analytic_account_id = bill.project_id.account_id

    @api.depends('contract_id', 'contract_id.sub_company_id', 'project_id', 'project_id.ages_contract_id')
    def _compute_sub_company_id(self):
        for bill in self:
            if bill.contract_id:
                bill.sub_company_id = bill.contract_id.sub_company_id
            elif bill.project_id and bill.project_id.ages_contract_id:
                bill.sub_company_id = bill.project_id.ages_contract_id.sub_company_id
            else:
                bill.sub_company_id = False

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if not self.contract_id:
            self.material_line_ids = [(5, 0, 0)]
            return
        contract = self.contract_id
        self.partner_id = contract.partner_id
        self.project_id = contract.project_id
        self.company_id = contract.company_id
        self.rebate_percent = contract.rebate_percent
        self.sales_tax_id = contract.sales_tax_id
        self.wth_tax_id = contract.wth_tax_id
        self.mobilization_percent = contract.mobilization_percent
        self.retention_percent = contract.retention_percent
        self.mobilization_amount_base = (
            contract.mobilization_amount_base
            or contract.company_id.ages_mobilization_amount_base
            or 'work_done_ex_rebate_mr'
        )
        self.retention_amount_base = (
            contract.retention_amount_base
            or contract.company_id.ages_retention_amount_base
            or 'work_done_ex_rebate_mr'
        )
        self.sales_tax_amount_base = (
            contract.sales_tax_amount_base
            or contract.company_id.ages_sales_tax_amount_base
            or 'work_done_ex_rebate_mr'
        )
        self.wht_on_mobilization = contract.wht_on_mobilization
        self.wht_on_retention = contract.wht_on_retention
        self.wth_on_sales_tax_id = contract.wth_on_sales_tax_id
        self.value_of_work_done = self._ages_get_remaining_work_done()
        # Prefill recovery materials with remaining qty from contract
        self.material_line_ids = self._prepare_material_line_commands(
            contract, exclude_bill_ids=self.ids
        )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.contract_id and self.contract_id.partner_id != self.partner_id:
            self.contract_id = False
            self.project_id = False
            self.material_line_ids = [(5, 0, 0)]

    @api.model
    def _prepare_material_line_commands(self, contract, exclude_bill_ids=None):
        """Build One2many commands to copy Recovery Material from a contract.

        Quantity is the remaining amount (contract qty minus other running bills).
        """
        exclude_ids = set(exclude_bill_ids or [])
        used_by_line = {}
        used_by_key = {}
        others = contract.running_bill_ids.filtered(
            lambda bill: bill.state != 'cancelled' and bill.id not in exclude_ids
        )
        for bill_line in others.mapped('material_line_ids'):
            if bill_line.contract_line_id:
                used_by_line[bill_line.contract_line_id.id] = (
                    used_by_line.get(bill_line.contract_line_id.id, 0.0)
                    + (bill_line.quantity or 0.0)
                )
            else:
                key = (bill_line.material, bill_line.uom_id.id)
                used_by_key[key] = used_by_key.get(key, 0.0) + (bill_line.quantity or 0.0)
        commands = [(5, 0, 0)]
        for line in contract.material_line_ids:
            used = used_by_line.get(line.id, 0.0) + used_by_key.get(
                (line.material, line.uom_id.id), 0.0
            )
            remaining = max((line.quantity or 0.0) - used, 0.0)
            commands.append((0, 0, {
                'contract_line_id': line.id,
                'material': line.material,
                'quantity': remaining,
                'uom_id': line.uom_id.id,
                'rate': line.rate,
            }))
        return commands

    # -------------------------------------------------------------------------
    # Amount helpers
    # -------------------------------------------------------------------------
    def _ages_format_work_done(self, amount):
        amount = amount or 0.0
        if abs(amount - round(amount)) < 0.005:
            return '%d' % int(round(amount))
        return '%.2f' % amount

    @api.depends('value_of_work_done', 'contract_id.total_work_done_value')
    def _compute_value_of_work_done_display(self):
        for bill in self:
            bill.value_of_work_done_display = '%s/%s' % (
                bill._ages_format_work_done(bill.value_of_work_done),
                bill._ages_format_work_done(bill.contract_id.total_work_done_value),
            )

    def _ages_get_remaining_work_done(self):
        """Contract total minus other non-cancelled running bills."""
        self.ensure_one()
        contract = self.contract_id
        if not contract:
            return 0.0
        others = contract.running_bill_ids.filtered(
            lambda other: other.state != 'cancelled' and other.id != self.id
        )
        used = sum(others.mapped('value_of_work_done'))
        return max((contract.total_work_done_value or 0) - used, 0.0)

    def _get_amount_for_base(self, base_key, a=None, c=None, e=None):
        """A / C / E mapping for Mobilization, Retention and Sales Tax bases."""
        self.ensure_one()
        mapping = {
            'total_work_done_value': self.value_of_work_done or 0.0 if a is None else a,
            'work_done_ex_rebate': self.ex_rebate_value or 0.0 if c is None else c,
            'work_done_ex_rebate_mr': self.ex_rebate_mr_value or 0.0 if e is None else e,
        }
        return mapping.get(base_key or '', 0.0)

    def _ages_get_wht_base_from_amounts(self, total_receivable, *args, **kwargs):
        """WHT base = Total Receivable (Inc Sales Tax)."""
        self.ensure_one()
        return total_receivable or 0.0

    def _get_wht_payment_base(self):
        """Same base as WTH Amount: Total Receivable (Inc Sales Tax)."""
        self.ensure_one()
        return self.total_receivable or 0.0

    def _ages_get_sales_tax_invoice_account(self):
        """Account from the sales tax invoice repartition line (tax type) — 80% client share."""
        self.ensure_one()
        tax = self.sales_tax_id
        if not tax:
            return self.env['account.account']
        lines = tax.invoice_repartition_line_ids.filtered(
            lambda line: line.repartition_type == 'tax' and line.account_id
        )
        if not lines and 'repartition_line_ids' in tax._fields:
            lines = tax.repartition_line_ids.filtered(
                lambda line: line.repartition_type == 'tax'
                and getattr(line, 'document_type', 'invoice') == 'invoice'
                and line.account_id
            )
        return lines[:1].account_id

    @api.depends(
        'invoice_move_ids.state',
        'invoice_move_ids.move_type',
        'invoice_move_ids.amount_total',
    )
    def _compute_invoiced_amount(self):
        for bill in self:
            invoices = bill.invoice_move_ids.filtered(
                lambda move: (
                    move.state == 'posted'
                    and move.move_type == 'out_invoice'
                )
            )
            bill.invoiced_amount = sum(invoices.mapped('amount_total'))

    def _ages_invoiced_sales_tax_amount(self):
        """Full sales tax amount booked as the positive SRB credit line (100%)."""
        self.ensure_one()
        return self.currency_id.round(abs(self.sales_tax_amount or 0.0))

    def _ages_invoiced_wth_on_sales_tax_amount(self):
        """WTH on Sales Tax booked as a negative line on the same SRB account (debit / 20%)."""
        self.ensure_one()
        return self.currency_id.round(abs(self.wth_on_sales_tax_amount or 0.0))

    def _ages_account_needs_payment_term(self, account):
        """Receivable/payable lines must be payment terms (with due date), not products."""
        return bool(account) and account.account_type in (
            'asset_receivable',
            'liability_payable',
        )

    def _ages_expected_invoice_total(self):
        """Invoice total = Work Done + 100% ST − WTH on ST − Mob (− Ret if product line).

        Retention on a receivable account is split from trade AR after create (payment
        term + due date), so it does not reduce amount_total as a product line.
        SRB ledger: credit 100%, debit 20% (net 80%).
        """
        self.ensure_one()
        company = self.company_id
        total = (
            abs(self.ex_rebate_mr_value or 0.0)
            + self._ages_invoiced_sales_tax_amount()
            - self._ages_invoiced_wth_on_sales_tax_amount()
        )
        mob_account = company.ages_mobilization_account_id
        if self.mobilization_amount and not self._ages_account_needs_payment_term(mob_account):
            total -= abs(self.mobilization_amount or 0.0)
        ret_account = company.ages_retention_account_id
        if self.retention_amount and not self._ages_account_needs_payment_term(ret_account):
            total -= abs(self.retention_amount or 0.0)
        return self.currency_id.round(total)

    @api.depends('material_line_ids.amount')
    def _compute_material_recovery(self):
        for bill in self:
            bill.material_recovery = sum(bill.material_line_ids.mapped('amount'))

    def _get_tax_amount(self, tax, base):
        """Compute tax amount for percent/fixed taxes against a base."""
        if not tax:
            return 0.0
        if tax.amount_type == 'fixed':
            return tax.amount or 0.0
        return base * (tax.amount or 0.0) / 100.0

    @api.depends(
        'value_of_work_done',
        'rebate_percent',
        'material_recovery',
        'sales_tax_id',
        'sales_tax_id.amount',
        'sales_tax_id.amount_type',
        'wth_tax_id',
        'wth_tax_id.amount',
        'wth_tax_id.amount_type',
        'mobilization_percent',
        'retention_percent',
        'mobilization_amount_base',
        'retention_amount_base',
        'sales_tax_amount_base',
        'wht_on_mobilization',
        'wht_on_retention',
        'wth_on_sales_tax_id',
        'wth_on_sales_tax_id.amount',
        'wth_on_sales_tax_id.amount_type',
    )
    def _compute_amount_fields(self):
        for bill in self:
            a = bill.value_of_work_done or 0.0
            b = a * (bill.rebate_percent or 0.0) / 100.0
            c = a - b
            d = bill.material_recovery or 0.0
            # E = C - D (Ex Rebate minus Material Recovery) — same as Contract logic
            e = c - d
            sales_base_map = {
                'total_work_done_value': a,
                'work_done_ex_rebate': c,
                'work_done_ex_rebate_mr': e,
            }
            sales_base = sales_base_map.get(
                bill.sales_tax_amount_base or 'work_done_ex_rebate_mr', e
            )
            bill.rebate_amount = b
            bill.ex_rebate_value = c
            bill.ex_rebate_mr_value = e
            mob_base = bill._get_amount_for_base(bill.mobilization_amount_base, a=a, c=c, e=e)
            ret_base = bill._get_amount_for_base(bill.retention_amount_base, a=a, c=c, e=e)
            h = mob_base * (bill.mobilization_percent or 0.0) / 100.0
            i = ret_base * (bill.retention_percent or 0.0) / 100.0
            # Sales Tax is always % × the selected Amount-Base (A / C / E).
            f = bill._get_tax_amount(bill.sales_tax_id, sales_base)
            # WTH on sales tax is deducted as a positive amount (tax % may be negative).
            wth_on_st = abs(bill._get_tax_amount(bill.wth_on_sales_tax_id, f) or 0.0)
            receivable_ex_st = e - i - h
            receivable_inc_st = receivable_ex_st + f
            # WHT base = Total Receivable (Inc Sales Tax), not Ex Rebate & MR.
            wht_base = bill._ages_get_wht_base_from_amounts(receivable_inc_st)
            wth = abs(bill._get_tax_amount(bill.wth_tax_id, wht_base) or 0.0)
            bill.sales_tax_amount = f
            bill.total_receivable_ex_sales_tax = receivable_ex_st
            bill.total_receivable = receivable_inc_st
            bill.wth_amount = wth
            bill.wth_on_sales_tax_amount = wth_on_st
            bill.mobilization_amount = h
            bill.retention_amount = i
            bill.net_amount = receivable_inc_st - wth_on_st - wth

    def _inverse_rebate_amount(self):
        for bill in self:
            if bill.value_of_work_done:
                bill.rebate_percent = round((bill.rebate_amount or 0.0) / bill.value_of_work_done * 100.0, 3)
            else:
                bill.rebate_percent = 0.0

    @api.onchange('rebate_amount')
    def _onchange_rebate_amount(self):
        if self.value_of_work_done:
            self.rebate_percent = round((self.rebate_amount or 0.0) / self.value_of_work_done * 100.0, 3)
        else:
            self.rebate_percent = 0.0
        self._compute_amount_fields()

    @api.onchange(
        'value_of_work_done',
        'rebate_percent',
        'material_recovery',
        'sales_tax_id',
        'wth_tax_id',
        'mobilization_percent',
        'retention_percent',
        'mobilization_amount_base',
        'retention_amount_base',
        'sales_tax_amount_base',
        'wht_on_mobilization',
        'wht_on_retention',
        'wth_on_sales_tax_id',
    )
    def _onchange_amount_trigger_fields(self):
        self._compute_amount_fields()

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) in (_('New'), 'New', False):
                vals['name'] = sequence.next_by_code('ages.running.bill') or _('New')
            if vals.get('contract_id'):
                contract = self.env['ages.contract'].browse(vals['contract_id'])
                if 'material_line_ids' not in vals:
                    vals['material_line_ids'] = [
                        cmd for cmd in self._prepare_material_line_commands(contract)
                        if cmd[0] != 5
                    ]
                if not vals.get('wth_tax_id') and contract.wth_tax_id:
                    vals['wth_tax_id'] = contract.wth_tax_id.id
                if not vals.get('wth_on_sales_tax_id') and contract.wth_on_sales_tax_id:
                    vals['wth_on_sales_tax_id'] = contract.wth_on_sales_tax_id.id
                if 'wht_on_mobilization' not in vals:
                    vals['wht_on_mobilization'] = contract.wht_on_mobilization
                if 'wht_on_retention' not in vals:
                    vals['wht_on_retention'] = contract.wht_on_retention
                if 'value_of_work_done' not in vals:
                    others = contract.running_bill_ids.filtered(lambda other: other.state != 'cancelled')
                    used = sum(others.mapped('value_of_work_done'))
                    vals['value_of_work_done'] = max((contract.total_work_done_value or 0) - used, 0)
        records = super().create(vals_list)
        records.with_context(skip_recompute_amount_fields=True)._compute_amount_fields()
        records._check_contract_work_done_capacity()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_recompute_amount_fields'):
            amount_trigger_fields = {
                'value_of_work_done', 'rebate_percent', 'rebate_amount', 'material_recovery',
                'sales_tax_id', 'wth_tax_id', 'mobilization_percent', 'retention_percent',
                'mobilization_amount_base', 'retention_amount_base', 'sales_tax_amount_base',
                'wht_on_mobilization', 'wht_on_retention', 'wth_on_sales_tax_id',
            }
            if any(field in vals for field in amount_trigger_fields):
                self.with_context(skip_recompute_amount_fields=True)._compute_amount_fields()
        if 'contract_id' in vals:
            for bill in self.filtered(lambda rec: rec.state == 'draft'):
                remaining = bill._ages_get_remaining_work_done()
                if bill.value_of_work_done != remaining:
                    super(AgesRunningBill, bill).write({'value_of_work_done': remaining})
        return res

    def _check_contract_work_done_capacity(self):
        """Block a new RA when existing bills already equal the contract total."""
        for bill in self:
            if bill.state == 'cancelled' or not bill.contract_id:
                continue
            contract = bill.contract_id
            existing = contract.running_bill_ids.filtered(
                lambda other: other.state != 'cancelled' and other.id != bill.id
            )
            if sum(existing.mapped('value_of_work_done')) >= (contract.total_work_done_value or 0):
                raise UserError(_(
                    'Running Bills already cover the contract Total Work Done Value (%s). '
                    'Unlock the contract, increase Total Work Done Value, then create another Running Bill.'
                ) % (contract.total_work_done_value or 0))

    def unlink(self):
        for bill in self:
            if bill.state == 'confirmed':
                raise UserError(_(
                    'You cannot delete a Confirmed Running Bill (%s). '
                    'Reset it first if you need to remove it.'
                ) % bill.display_name)
        return super().unlink()

    @api.model
    def create_from_contract(self, contract):
        """Factory used by Contract → Create RA Bill."""
        contract.ensure_one()
        company = contract.company_id
        remaining = max(
            (contract.total_work_done_value or 0) - (contract.running_bills_work_done or 0),
            0,
        )
        return self.create({
            'partner_id': contract.partner_id.id,
            'contract_id': contract.id,
            'project_id': contract.project_id.id,
            'company_id': company.id,
            'date': fields.Date.context_today(self),
            'value_of_work_done': remaining,
            'rebate_percent': contract.rebate_percent,
            'sales_tax_id': contract.sales_tax_id.id,
            'wth_tax_id': contract.wth_tax_id.id,
            'wth_on_sales_tax_id': contract.wth_on_sales_tax_id.id,
            'wht_on_mobilization': contract.wht_on_mobilization,
            'wht_on_retention': contract.wht_on_retention,
            'mobilization_percent': contract.mobilization_percent,
            'retention_percent': contract.retention_percent,
            'mobilization_amount_base': (
                contract.mobilization_amount_base
                or company.ages_mobilization_amount_base
                or 'work_done_ex_rebate_mr'
            ),
            'retention_amount_base': (
                contract.retention_amount_base
                or company.ages_retention_amount_base
                or 'work_done_ex_rebate_mr'
            ),
            'sales_tax_amount_base': (
                contract.sales_tax_amount_base
                or company.ages_sales_tax_amount_base
                or 'work_done_ex_rebate_mr'
            ),
            'material_line_ids': [
                cmd for cmd in self._prepare_material_line_commands(contract)
                if cmd[0] != 5
            ],
        })

    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for bill in self:
            if bill.state != 'draft':
                raise UserError(_('Only Draft running bills can be confirmed.'))
            bill._check_confirm_ready()
            invoice = bill._create_and_post_invoice()
            bill.write({
                'state': 'confirmed',
                'invoice_id': invoice.id,
            })
        return True

    def action_cancel(self):
        for bill in self:
            if bill.state != 'draft':
                raise UserError(_('Only Draft running bills can be cancelled.'))
            bill.state = 'cancelled'
        return True

    def action_reset(self):
        """Reset Running Bill to Draft and reverse/remove the linked invoice."""
        for bill in self:
            if bill.state not in ('confirmed', 'cancelled'):
                raise UserError(_('Only Confirmed or Cancelled running bills can be reset.'))
            invoice = bill.invoice_id
            if invoice:
                if invoice.payment_state in ('paid', 'partial', 'in_payment'):
                    raise UserError(_(
                        'You cannot reset Running Bill %s because linked invoice %s has payments.'
                    ) % (bill.display_name, invoice.display_name))
                if invoice.state == 'posted':
                    invoice.button_draft()
                if invoice.state == 'draft':
                    invoice.button_cancel()
                if invoice.state == 'cancel':
                    invoice.with_context(force_delete=True).unlink()
                else:
                    raise UserError(_(
                        'Unable to reset linked invoice %s. Please reset/cancel it manually.'
                    ) % invoice.display_name)
            bill.write({
                'state': 'draft',
                'invoice_id': False,
            })
        return True

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_contract(self):
        self.ensure_one()
        if not self.contract_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract'),
            'res_model': 'ages.contract',
            'res_id': self.contract_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _check_confirm_ready(self):
        self.ensure_one()
        if not self.partner_id or not self.contract_id or not self.project_id:
            raise UserError(_('Client, Contract and Project are required.'))
        if not self.date:
            raise UserError(_('Date is required.'))
        company = self.company_id
        missing = []
        if not company.ages_work_done_account_id:
            missing.append(_('Work Done Account'))
        if self.mobilization_amount and not company.ages_mobilization_account_id:
            missing.append(_('Mobilization Account'))
        if self.retention_amount and not company.ages_retention_account_id:
            missing.append(_('Retention Account'))
        if missing:
            raise UserError(_(
                'Please configure these Default Accounts in Project → Configuration → Settings: %s'
            ) % ', '.join(missing))

    # -------------------------------------------------------------------------
    # Invoice generation
    # -------------------------------------------------------------------------
    def _ages_assert_product_line_account(self, account, label, allow_receivable=False):
        """Normal RA product lines cannot use Payable / Off-Balance.

        Retention (and sometimes Mobilization) may legitimately be Receivable —
        money still owed by the client but held back. Those are booked as extra
        payment-term (receivable) lines, not as product lines.
        """
        self.ensure_one()
        if not account:
            raise UserError(_('%s account is not configured.') % label)
        bad_types = ['liability_payable', 'off_balance']
        if not allow_receivable:
            bad_types.append('asset_receivable')
        if account.account_type in bad_types:
            raise UserError(_(
                '%(label)s uses account %(account)s with type "%(atype)s".\n'
                'This line must use income / expense / current liability '
                '(or Receivable only for Retention / Mobilization client holds).\n'
                'Fix this in Project → Configuration → Settings (or on the Sales Tax).'
            ) % {
                'label': label,
                'account': account.display_name,
                'atype': account.account_type,
            })

    def _ages_prepare_invoice_line_command(self, name, price_unit, account, analytic_dist):
        self.ensure_one()
        return Command.create({
            'name': name,
            'display_type': 'product',
            'quantity': 1.0,
            'price_unit': price_unit,
            'account_id': account.id,
            # Explicit empty taxes — accounts may have default taxes that unbalance RA invoices.
            'tax_ids': [Command.set([])],
            'analytic_distribution': analytic_dist or False,
        })

    def _ages_invoice_balance_diff(self, invoice):
        currency = invoice.company_currency_id or invoice.currency_id
        return currency.round(sum(invoice.line_ids.mapped('balance')))

    def _ages_raise_unbalanced_invoice(self, invoice, imbalance):
        details = '\n'.join(
            '%s | %s | debit=%s credit=%s'
            % (
                line.account_id.code or '-',
                line.name or line.display_type,
                line.debit,
                line.credit,
            )
            for line in invoice.line_ids.sorted(
                lambda line: (line.account_id.code or '', line.id)
            )
        )
        invoice.with_context(check_move_validity=False, dynamic_unlink=True).unlink()
        raise UserError(_(
            'The Running Bill invoice is not balanced (difference: %(diff)s).\n\n'
            'Lines:\n%(details)s'
        ) % {'diff': imbalance, 'details': details})

    def _ages_ensure_trade_receivable(self, invoice):
        """Create/rebuild the trade receivable payment-term line to balance product lines.

        Writing the same price_unit is a no-op in the ORM, so Odoo may never recreate
        the AR line after we clear taxes / payment terms. Do it explicitly.
        """
        self.ensure_one()
        currency = invoice.company_currency_id
        ctx = {'check_move_validity': False, 'dynamic_unlink': True}

        term_lines = invoice.line_ids.filtered(lambda line: line.display_type == 'payment_term')
        if term_lines:
            term_lines.with_context(**ctx).unlink()

        # Remaining lines (product / tax / etc.) must be offset by receivable.
        non_term_balance = currency.round(
            sum(invoice.line_ids.mapped('balance'))
        )
        # out_invoice product credits → negative balance; AR needs positive debit.
        needed = currency.round(-non_term_balance)
        if currency.is_zero(needed):
            return

        partner = invoice.commercial_partner_id or invoice.partner_id
        ar_account = partner.with_company(invoice.company_id).property_account_receivable_id
        if not ar_account:
            raise UserError(_(
                'Customer %s has no Accounts Receivable account. '
                'Set it on the partner before confirming the Running Bill.'
            ) % partner.display_name)

        debit = needed if needed > 0 else 0.0
        credit = -needed if needed < 0 else 0.0
        amount_currency = needed
        if invoice.currency_id and invoice.currency_id != currency:
            # Invoice currency amount equals company amount when rate is handled by Odoo;
            # for company-currency RA bills this matches needed.
            amount_currency = invoice.currency_id.round(needed)

        vals = {
            'move_id': invoice.id,
            'name': invoice.payment_reference or invoice.name or invoice.ref or '/',
            'display_type': 'payment_term',
            'account_id': ar_account.id,
            'partner_id': partner.id,
            'debit': debit,
            'credit': credit,
            'date_maturity': invoice.invoice_date_due or invoice.invoice_date or invoice.date,
            'currency_id': (invoice.currency_id or currency).id,
            'amount_currency': amount_currency if debit else -amount_currency,
        }
        if self.analytic_account_id:
            vals['analytic_distribution'] = {str(self.analytic_account_id.id): 100}
        self.env['account.move.line'].with_context(**ctx).create(vals)

    def _ages_finalize_running_bill_invoice(self, invoice):
        """Strip auto taxes and rebuild payment terms so the RA invoice stays balanced."""
        self.ensure_one()
        ctx = {'check_move_validity': False, 'dynamic_unlink': True}

        product_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == 'product'
        )
        if product_lines.tax_ids:
            product_lines.with_context(**ctx).write({'tax_ids': [Command.set([])]})

        tax_lines = invoice.line_ids.filtered(lambda line: line.display_type == 'tax')
        if tax_lines:
            tax_lines.with_context(**ctx).unlink()

        # Explicit trade AR — do not rely on a no-op price_unit write to sync terms.
        self._ages_ensure_trade_receivable(invoice)

        imbalance = self._ages_invoice_balance_diff(invoice)
        if imbalance:
            self._ages_raise_unbalanced_invoice(invoice, imbalance)
        return invoice

    def _ages_split_receivable_hold(self, invoice, account, amount, label):
        """Move part of trade receivable onto a client-hold receivable account.

        Retention (and similar holds) are still receivable from the client, but on
        a dedicated AR account. Odoo requires receivable accounts to be payment-term
        lines, so we split the main AR line instead of posting a product line.
        """
        self.ensure_one()
        company_currency = invoice.company_currency_id
        amount = company_currency.round(abs(amount or 0.0))
        if company_currency.is_zero(amount):
            return

        ctx = {'check_move_validity': False}
        term_lines = invoice.line_ids.filtered(
            lambda line: line.display_type == 'payment_term' and line.debit > 0
        )
        if not term_lines:
            raise UserError(_(
                'Cannot book %s on receivable account %s: invoice has no receivable line.'
            ) % (label, account.display_name))

        main = term_lines.sorted(lambda line: -line.debit)[0]
        if company_currency.compare_amounts(main.debit, amount) < 0:
            raise UserError(_(
                'Cannot book %(label)s (%(amount)s): trade receivable is only %(debit)s.'
            ) % {
                'label': label,
                'amount': amount,
                'debit': main.debit,
            })

        new_debit = company_currency.round(main.debit - amount)
        main_vals = {
            'debit': new_debit,
            'credit': 0.0,
        }
        if main.currency_id == company_currency or not main.currency_id:
            main_vals['amount_currency'] = new_debit
        else:
            # Keep the same FX rate as the original receivable line.
            rate = (main.amount_currency / main.debit) if main.debit else 1.0
            main_vals['amount_currency'] = main.currency_id.round(new_debit * rate)
        main.with_context(**ctx).write(main_vals)

        hold_vals = {
            'move_id': invoice.id,
            'name': label,
            'display_type': 'payment_term',
            'account_id': account.id,
            'partner_id': invoice.partner_id.id,
            'debit': amount,
            'credit': 0.0,
            'date_maturity': main.date_maturity or invoice.invoice_date or invoice.date,
            'currency_id': main.currency_id.id,
        }
        if main.currency_id == company_currency or not main.currency_id:
            hold_vals['amount_currency'] = amount
        else:
            rate = (main.amount_currency / (new_debit + amount)) if (new_debit + amount) else 1.0
            hold_vals['amount_currency'] = main.currency_id.round(amount * rate)
        if self.analytic_account_id:
            hold_vals['analytic_distribution'] = {str(self.analytic_account_id.id): 100}

        self.env['account.move.line'].with_context(**ctx).create(hold_vals)

    def _create_and_post_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            raise UserError(_('An invoice is already linked to this Running Bill.'))

        company = self.company_id
        analytic_dist = {}
        if self.analytic_account_id:
            analytic_dist = {str(self.analytic_account_id.id): 100}

        work_done_account = company.ages_work_done_account_id
        self._ages_assert_product_line_account(work_done_account, _('Work Done'))

        line_cmds = []

        # E — Work Done (no tax on this line; sales tax is separate lines)
        line_cmds.append(self._ages_prepare_invoice_line_command(
            _('Work Done'),
            self.ex_rebate_mr_value,
            work_done_account,
            analytic_dist,
        ))

        # Sales Tax on SRB: credit 100%, then debit WTH share (20%) on the same account
        # so the SRB ledger net effect is 80%. Both lines post (no note-only 20%).
        full_sales_tax = self._ages_invoiced_sales_tax_amount()
        withheld_sales_tax = self._ages_invoiced_wth_on_sales_tax_amount()
        tax_account = self.env['account.account']
        if self.sales_tax_id and full_sales_tax:
            tax_account = self._ages_get_sales_tax_invoice_account()
            if not tax_account:
                raise UserError(_(
                    'Sales Tax "%s" has no account on its invoice tax repartition line. '
                    'Set Account on Accounting → Taxes → %s before confirming.'
                ) % (self.sales_tax_id.display_name, self.sales_tax_id.display_name))
            self._ages_assert_product_line_account(tax_account, _('Sales Tax'))
            line_cmds.append(self._ages_prepare_invoice_line_command(
                _('Sales Tax (%s%%)') % (self.sales_tax_id.amount,),
                full_sales_tax,
                tax_account,
                analytic_dist,
            ))
        if withheld_sales_tax:
            if not tax_account:
                tax_account = self._ages_get_sales_tax_invoice_account()
            if not tax_account:
                raise UserError(_(
                    'WTH on Sales Tax requires the Sales Tax payable account. '
                    'Set Account on the Sales Tax invoice repartition line.'
                ))
            self._ages_assert_product_line_account(tax_account, _('WTH on Sales Tax'))
            line_cmds.append(self._ages_prepare_invoice_line_command(
                _('WTH on Sales Tax (client withheld)'),
                -withheld_sales_tax,
                tax_account,
                analytic_dist,
            ))

        # Mobilization / Retention: product lines only when the account is NOT
        # receivable/payable (those need due date → payment-term split below).
        retention_hold_account = self.env['account.account']
        mobilization_hold_account = self.env['account.account']
        if self.mobilization_amount:
            mob_account = company.ages_mobilization_account_id
            if self._ages_account_needs_payment_term(mob_account):
                mobilization_hold_account = mob_account
            else:
                self._ages_assert_product_line_account(mob_account, _('Mobilization'))
                line_cmds.append(self._ages_prepare_invoice_line_command(
                    _('Mobilization Recovery (%s%%)') % (self.mobilization_percent or 0.0,),
                    -abs(self.mobilization_amount),
                    mob_account,
                    analytic_dist,
                ))
        if self.retention_amount:
            ret_account = company.ages_retention_account_id
            if self._ages_account_needs_payment_term(ret_account):
                retention_hold_account = ret_account
            else:
                self._ages_assert_product_line_account(ret_account, _('Retention'))
                line_cmds.append(self._ages_prepare_invoice_line_command(
                    _('Retained Amount (%s%%)') % (self.retention_percent or 0.0,),
                    -abs(self.retention_amount),
                    ret_account,
                    analytic_dist,
                ))

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.date,
            'date': self.date,
            'company_id': company.id,
            'currency_id': self.currency_id.id,
            'invoice_origin': self.name,
            'ref': self.name,
            'ages_contract_id': self.contract_id.id,
            'ages_project_id': self.project_id.id,
            'ages_running_bill_id': self.id,
            'ages_sub_company_id': self.sub_company_id.id,
            'invoice_line_ids': line_cmds,
        }
        if 'ages_analytic_account_id' in self.env['account.move']._fields:
            invoice_vals['ages_analytic_account_id'] = self.analytic_account_id.id

        # check_move_validity=False: create even if account default taxes briefly unbalance
        # the move; we clear taxes and rebuild receivable before posting.
        # ages_skip_analytic_apply: analytic already set on lines — avoid a post-create
        # write that can re-trigger tax/payment-term sync and break the balance.
        Move = self.env['account.move'].with_company(company).with_context(
            check_move_validity=False,
            ages_skip_analytic_apply=True,
        )
        invoice = Move.create(invoice_vals)
        self._ages_finalize_running_bill_invoice(invoice)

        # Retention (and Mob if receivable) must be payment-term lines with due date.
        if mobilization_hold_account and self.mobilization_amount:
            self._ages_split_receivable_hold(
                invoice,
                mobilization_hold_account,
                self.mobilization_amount,
                _('Mobilization Recovery (%s%%)') % (self.mobilization_percent or 0.0,),
            )
        if retention_hold_account and self.retention_amount:
            self._ages_split_receivable_hold(
                invoice,
                retention_hold_account,
                self.retention_amount,
                _('Retained Amount (%s%%)') % (self.retention_percent or 0.0,),
            )

        imbalance = self._ages_invoice_balance_diff(invoice)
        if imbalance:
            self._ages_raise_unbalanced_invoice(invoice, imbalance)

        invoice.action_post()
        return invoice

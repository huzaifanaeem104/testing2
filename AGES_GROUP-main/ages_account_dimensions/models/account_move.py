# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.tools.float_utils import float_compare, float_is_zero


class AccountMove(models.Model):
    _inherit = 'account.move'

    move_type = fields.Selection(selection_add=[
        ('out_invoice', 'Client Invoice'),
        ('out_refund', 'Client Credit Note'),
        ('out_receipt', 'Client Receipt'),
    ])

    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        copy=True,
        index=True,
        check_company=True,
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
    ages_wth_amount_display = fields.Char(
        string='WTH Amount (Rs)',
        compute='_compute_ages_running_bill_wht_display',
        help='Format: Expected / Recorded on this invoice.\n'
             'Expected = Running Bill WTH Amount (Rs). '
             'Recorded = income WTH already posted on payments reconciled to this invoice.',
    )
    ages_wth_on_sales_tax_display = fields.Char(
        string='WTH on Sales Tax',
        compute='_compute_ages_running_bill_wht_display',
        help='Format: Expected / Recorded on this invoice.\n'
             'Expected = Running Bill WTH on Sales Tax. '
             'Recorded = WTH on Sales Tax already posted on payments of this invoice '
             '(normally 0 — SRB share is booked on the invoice, not on Pay).',
    )

    def _ages_format_wht_pair(self, running_bill_amount, posted_amount):
        def _fmt(amount):
            amount = abs(amount or 0.0)
            if abs(amount - round(amount)) < 0.005:
                return '%d' % int(round(amount))
            return '%.2f' % amount
        return '%s/%s' % (_fmt(running_bill_amount), _fmt(posted_amount))

    def _ages_get_posted_running_bill_payments(self, extra_payments=None):
        """Payments linked to this running bill (bill-wide — used by Pay remaining/cap)."""
        self.ensure_one()
        payments = self.reconciled_payment_ids
        if extra_payments is not None:
            payments |= extra_payments
        elif self.ages_running_bill_id:
            payments |= self.env['account.payment'].search([
                ('ages_running_bill_id', '=', self.ages_running_bill_id.id),
                ('state', 'in', ('in_process', 'paid')),
            ])
        return payments.filtered(lambda payment: payment.state in ('in_process', 'paid'))

    def _ages_get_invoice_recorded_wht_payments(self):
        """Payments reconciled to THIS invoice only (for header Expected/Recorded display)."""
        self.ensure_one()
        return self.reconciled_payment_ids.filtered(
            lambda payment: payment.state in ('in_process', 'paid')
        )

    def _ages_sum_posted_withholding(self, payments, taxes):
        if not taxes:
            return 0.0
        tax_ids = set(taxes.ids)
        total = 0.0
        for payment in payments:
            for line in payment.withholding_line_ids:
                line_taxes = line.tax_id
                if 'source_tax_id' in line._fields and line.source_tax_id:
                    line_taxes |= line.source_tax_id
                if line_taxes.ids and tax_ids.intersection(line_taxes.ids):
                    total += abs(line.amount or 0.0)
        return total

    @api.depends(
        'ages_running_bill_id',
        'ages_running_bill_id.wth_amount',
        'ages_running_bill_id.wth_on_sales_tax_amount',
        'ages_running_bill_id.wth_tax_id',
        'ages_running_bill_id.wth_on_sales_tax_id',
        'reconciled_payment_ids',
        'reconciled_payment_ids.state',
        'reconciled_payment_ids.withholding_line_ids.amount',
        'reconciled_payment_ids.withholding_line_ids.tax_id',
    )
    def _compute_ages_running_bill_wht_display(self):
        moves_with_bill = self.filtered(lambda move: move.ages_running_bill_id)
        for move in self - moves_with_bill:
            move.ages_wth_amount_display = False
            move.ages_wth_on_sales_tax_display = False
        if not moves_with_bill:
            return

        tax_cache = {}
        Tax = self.env['account.tax']
        for move in moves_with_bill:
            bill = move.ages_running_bill_id
            # Header slash = Expected (bill) / Recorded on THIS invoice only.
            # Bill-wide payments are still used by Pay remaining/cap separately.
            payments = move._ages_get_invoice_recorded_wht_payments()
            wth_taxes = bill.wth_tax_id
            sales_tax_wht = bill.wth_on_sales_tax_id
            if sales_tax_wht and not sales_tax_wht.is_withholding_tax_on_payment:
                cache_key = (
                    (sales_tax_wht.company_id or move.company_id).id,
                    sales_tax_wht.amount,
                )
                if cache_key not in tax_cache:
                    tax_cache[cache_key] = Tax.search([
                        *Tax._check_company_domain(sales_tax_wht.company_id or move.company_id),
                        ('is_withholding_tax_on_payment', '=', True),
                        ('type_tax_use', '=', 'sale'),
                        ('amount', '=', sales_tax_wht.amount),
                        ('active', '=', True),
                    ], limit=1)
                sales_tax_wht |= tax_cache[cache_key]
            move.ages_wth_amount_display = move._ages_format_wht_pair(
                bill.wth_amount,
                move._ages_sum_posted_withholding(payments, wth_taxes),
            )
            move.ages_wth_on_sales_tax_display = move._ages_format_wht_pair(
                bill.wth_on_sales_tax_amount,
                move._ages_sum_posted_withholding(payments, sales_tax_wht),
            )

    def _ages_contract_from_project(self, project):
        if not project:
            return self.env['ages.contract']
        project = project.sudo()
        if project.ages_contract_id:
            return project.ages_contract_id
        if 'ages_contract_ids' in project._fields and len(project.ages_contract_ids) == 1:
            return project.ages_contract_ids
        return self.env['ages.contract']

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

    def _ages_guess_contract(self):
        """Contract from linked source document or the selected project."""
        self.ensure_one()
        if self.ages_contract_id:
            return self.ages_contract_id
        for fname in (
            'ages_running_bill_id',
            'ages_mobilization_advance_id',
            'ages_retention_recovery_id',
            'ages_material_consumption_id',
        ):
            source = self[fname] if fname in self._fields else False
            if source and source.contract_id:
                return source.contract_id
        if self.origin_payment_id:
            return self.env['ages.contract']
        return self._ages_contract_from_project(self.ages_project_id)

    def _ages_apply_contract(self, contract):
        """Fill project / analytic / active company from a contract."""
        self.ensure_one()
        if not contract:
            return
        if contract.project_id:
            self.ages_project_id = contract.project_id
        if contract.analytic_account_id:
            self.ages_analytic_account_id = contract.analytic_account_id
        elif contract.project_id.account_id:
            self.ages_analytic_account_id = contract.project_id.account_id
        if contract.sub_company_id:
            self.ages_sub_company_id = contract.sub_company_id

    @api.onchange('ages_sub_company_id')
    def _onchange_ages_sub_company_id(self):
        domain = self._ages_project_domain()
        if (
            self.ages_project_id
            and self.ages_sub_company_id
            and not self._ages_project_belongs_to_sub_company(
                self.ages_project_id, self.ages_sub_company_id
            )
        ):
            self.ages_project_id = False
            self.ages_analytic_account_id = False
            self.ages_contract_id = False
        return {'domain': {'ages_project_id': domain}}

    @api.onchange('ages_contract_id')
    def _onchange_ages_contract_id(self):
        if self.ages_contract_id:
            self._ages_apply_contract(self.ages_contract_id)
        self._ages_apply_analytic_to_lines_ui()

    @api.onchange('ages_project_id')
    def _onchange_ages_project_id(self):
        if self.ages_project_id:
            self.ages_analytic_account_id = self.ages_project_id.account_id
            contract = self.ages_contract_id
            if contract and contract.project_id and contract.project_id != self.ages_project_id:
                contract = self.env['ages.contract']
                self.ages_contract_id = False
            if not contract:
                contract = self._ages_contract_from_project(self.ages_project_id)
                if contract:
                    self.ages_contract_id = contract
            sub_company = self._ages_sub_company_from_project(self.ages_project_id)
            if sub_company:
                self.ages_sub_company_id = sub_company
            elif contract and contract.sub_company_id:
                self.ages_sub_company_id = contract.sub_company_id
            if self.ages_project_id.company_id:
                self.company_id = self.ages_project_id.company_id
        else:
            self.ages_analytic_account_id = False
        self._ages_apply_analytic_to_lines_ui()

    @api.onchange('ages_analytic_account_id')
    def _onchange_ages_analytic_account_id(self):
        self._ages_apply_analytic_to_lines_ui()

    def _ages_project_domain(self):
        self.ensure_one()
        domain = []
        if self.company_id:
            domain.append(('company_id', 'in', [self.company_id.id, False]))
        if self.ages_sub_company_id:
            domain.append(('ages_contract_id.sub_company_id', '=', self.ages_sub_company_id.id))
        return domain

    def _ages_analytic_distribution(self):
        self.ensure_one()
        if not self.ages_analytic_account_id:
            return False
        return {str(self.ages_analytic_account_id.id): 100}

    def _ages_apply_analytic_to_lines_ui(self):
        """Apply analytic distribution on in-memory invoice/journal lines (onchange)."""
        dist = self._ages_analytic_distribution()
        for line in self.invoice_line_ids | self.line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue
            line.analytic_distribution = dist

    def _ages_apply_analytic_distribution(self):
        """Persist analytic distribution on all real move lines."""
        for move in self:
            dist = move._ages_analytic_distribution()
            if not dist:
                continue
            lines = (move.line_ids | move.invoice_line_ids).filtered(
                lambda line: line.display_type not in ('line_section', 'line_note')
            )
            if lines:
                lines.write({'analytic_distribution': dist})

    def _ages_skip_contract_from_project(self, vals=None):
        """Direct payment entries must not guess a contract from the project."""
        vals = vals or {}
        if vals.get('origin_payment_id'):
            return True
        return bool(self) and all(move.origin_payment_id for move in self)

    def _ages_fill_contract_vals(self, vals):
        """Ensure contract (and related dimensions) are set from the source."""
        skip_project_contract = self._ages_skip_contract_from_project(vals)
        if vals.get('ages_contract_id'):
            contract = self.env['ages.contract'].sudo().browse(vals['ages_contract_id'])
        else:
            contract = self.env['ages.contract']
            for fname, model_name in (
                ('ages_running_bill_id', 'ages.running.bill'),
                ('ages_mobilization_advance_id', 'ages.mobilization.advance'),
                ('ages_retention_recovery_id', 'ages.retention.recovery'),
                ('ages_material_consumption_id', 'ages.material.consumption'),
            ):
                if vals.get(fname) and model_name in self.env:
                    source = self.env[model_name].sudo().browse(vals[fname])
                    if source.contract_id:
                        contract = source.contract_id
                        break
            if not contract and vals.get('ages_project_id') and not skip_project_contract:
                contract = self._ages_contract_from_project(
                    self.env['project.project'].browse(vals['ages_project_id'])
                )
            if contract:
                vals['ages_contract_id'] = contract.id
        if contract:
            contract = contract.sudo()
            if contract.project_id and not vals.get('ages_project_id'):
                vals['ages_project_id'] = contract.project_id.id
            if contract.sub_company_id and not vals.get('ages_sub_company_id'):
                vals['ages_sub_company_id'] = contract.sub_company_id.id
            if not vals.get('ages_analytic_account_id'):
                analytic = contract.analytic_account_id or contract.project_id.account_id
                if analytic:
                    vals['ages_analytic_account_id'] = analytic.id
        if not vals.get('ages_sub_company_id') and vals.get('ages_project_id'):
            sub_company = self._ages_sub_company_from_project(
                self.env['project.project'].browse(vals['ages_project_id'])
            )
            if sub_company:
                vals['ages_sub_company_id'] = sub_company.id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ages_fill_contract_vals(vals)
            if vals.get('ages_project_id') and not vals.get('ages_analytic_account_id'):
                project = self.env['project.project'].sudo().browse(vals['ages_project_id'])
                if project.account_id:
                    vals['ages_analytic_account_id'] = project.account_id.id
            if vals.get('ages_project_id') and not vals.get('ages_sub_company_id'):
                sub_company = self._ages_sub_company_from_project(
                    self.env['project.project'].browse(vals['ages_project_id'])
                )
                if sub_company:
                    vals['ages_sub_company_id'] = sub_company.id
        moves = super().create(vals_list)
        moves.filtered(
            lambda move: not move.ages_contract_id and not move.origin_payment_id
        )._ages_fill_missing_contract()
        if not self.env.context.get('ages_skip_analytic_apply'):
            moves.filtered('ages_analytic_account_id')._ages_apply_analytic_distribution()
        return moves

    def _ages_fill_missing_contract(self):
        for move in self:
            contract = move._ages_guess_contract()
            if contract:
                move.ages_contract_id = contract.id

    def write(self, vals):
        if any(key in vals for key in (
            'ages_contract_id', 'ages_project_id', 'ages_running_bill_id',
            'ages_mobilization_advance_id', 'ages_retention_recovery_id',
        )):
            vals = self._ages_fill_contract_vals(dict(vals))
        if vals.get('ages_project_id') and 'ages_analytic_account_id' not in vals:
            project = self.env['project.project'].sudo().browse(vals['ages_project_id'])
            if project.account_id:
                vals = dict(vals, ages_analytic_account_id=project.account_id.id)
            if 'ages_sub_company_id' not in vals:
                sub_company = self._ages_sub_company_from_project(project)
                if sub_company:
                    vals = dict(vals, ages_sub_company_id=sub_company.id)
        res = super().write(vals)
        if any(key in vals for key in ('ages_analytic_account_id', 'ages_project_id', 'ages_contract_id')):
            self._ages_apply_analytic_distribution()
        return res

    def _ages_needs_skip_invoice_sync_on_draft(self):
        """Payment / WHT entries must not run tax sync when resetting to draft.

        Odoo treats lines with tax_repartition_line_id as tax lines. On draft reset,
        _sync_tax_lines can delete the withholding tax AML and leave liquidity vs
        receivable/payable unbalanced ("The entry is not balanced.").
        """
        self.ensure_one()
        if not self.is_entry():
            return False
        if self.origin_payment_id:
            return True
        return bool(self.line_ids.tax_repartition_line_id)

    def button_draft(self):
        skip_sync = self.filtered(lambda move: move._ages_needs_skip_invoice_sync_on_draft())
        normal = self - skip_sync
        if skip_sync:
            super(AccountMove, skip_sync.with_context(skip_invoice_sync=True)).button_draft()
        if normal:
            super(AccountMove, normal).button_draft()
        return True

    def _ages_withheld_sales_tax_refund_ref(self):
        self.ensure_one()
        return 'AGES-SRB-WHT:%s' % self.id

    def _ages_existing_withheld_sales_tax_refund(self):
        self.ensure_one()
        return self.search([
            ('move_type', '=', 'out_refund'),
            ('reversed_entry_id', '=', self.id),
            ('ref', '=', self._ages_withheld_sales_tax_refund_ref()),
            ('state', '!=', 'cancel'),
        ], limit=1)

    def _ages_clear_withheld_sales_tax(self):
        """Credit the WTH on Sales Tax share on older 100% sales-tax invoices."""
        refunds = self.env['account.move']
        for invoice in self:
            refunds |= invoice._ages_clear_withheld_sales_tax_invoice()
        return refunds

    def _ages_clear_withheld_sales_tax_invoice(self):
        """No longer create AGES-SRB-WHT credit notes.

        Running-bill invoices book SRB credit 100% and debit the WTH share, so these
        temporary refunds must not be recreated (they clutter ledgers).
        """
        self.ensure_one()
        return self.env['account.move']

    def _ages_cancel_withheld_sales_tax_refunds(self):
        """Cancel posted/draft AGES-SRB-WHT temporary credit notes."""
        refunds = self.search([
            ('move_type', '=', 'out_refund'),
            ('ref', '=like', 'AGES-SRB-WHT:%'),
            ('state', 'in', ('draft', 'posted')),
        ])
        for refund in refunds:
            refund.line_ids.remove_move_reconcile()
            if refund.state == 'posted':
                refund.button_draft()
            if refund.state == 'draft':
                refund.button_cancel()
        return refunds

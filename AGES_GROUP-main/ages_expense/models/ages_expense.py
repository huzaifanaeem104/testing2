# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class AgesExpense(models.Model):
    _name = 'ages.expense'
    _description = 'Vendor Expense'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Voucher No',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
        index=True,
    )
    description = fields.Char(
        string='Description',
        required=True,
        tracking=True,
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain="['|', ('supplier_rank', '>', 0), ('is_company', '=', True)]",
        required=False,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    # Kept for backward compatibility / optional reporting; project is selected on lines.
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=False,
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        compute='_compute_header_from_lines',
        store=True,
        readonly=True,
    )
    sub_company_id = fields.Many2one(
        'ages.sub.company',
        string='Active Company',
        compute='_compute_header_from_lines',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_header_from_lines',
        store=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Payment Account',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        required=True,
        tracking=True,
    )
    apply_100_payment_analytic = fields.Boolean(
        string='Apply 100% Payment Analytic Distribution',
        default=True,
        tracking=True,
        help='When enabled, the selected Analytic Account is applied at 100% '
             'on the payment/liquidity journal item only. Not used when the '
             'payment journal is a Bank journal.',
    )
    payment_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        tracking=True,
        help='Applied at 100% on the payment/liquidity journal item when '
             'Apply 100% Payment Analytic Distribution is enabled.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='journal_id.currency_id',
        readonly=True,
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Payment Entry',
        readonly=True,
        copy=False,
    )
    line_ids = fields.One2many(
        'ages.expense.line',
        'expense_id',
        string='Expenses Notebook',
    )
    total_amount = fields.Monetary(
        string='Total',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection([
        ('new', 'New'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='new', required=True, tracking=True)

    @api.depends(
        'line_ids.project_id',
        'line_ids.analytic_account_id',
        'line_ids.project_id.ages_sub_company_id',
        'line_ids.project_id.company_id',
    )
    def _compute_header_from_lines(self):
        for rec in self:
            lines = rec.line_ids.filtered('project_id')
            if not lines:
                rec.analytic_account_id = False
                rec.sub_company_id = False
                rec.company_id = rec.env.company
                continue

            # Prefer values from the first line; company must be consistent enough for payment.
            first = lines[0]
            rec.analytic_account_id = first.analytic_account_id
            sub = first._ages_get_sub_company()
            rec.sub_company_id = sub
            if sub and sub.company_id:
                rec.company_id = sub.company_id
            elif first.project_id.company_id:
                rec.company_id = first.project_id.company_id
            else:
                rec.company_id = rec.env.company

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(line.amount for line in rec.line_ids)

    def _ages_is_bank_journal(self):
        self.ensure_one()
        return bool(self.journal_id) and self.journal_id.type == 'bank'

    def _ages_apply_bank_journal_vals(self, vals):
        journal_id = vals.get('journal_id')
        if not journal_id:
            return
        journal = self.env['account.journal'].browse(journal_id)
        if journal.type == 'bank':
            vals['apply_100_payment_analytic'] = False
            vals['payment_analytic_account_id'] = False

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self._ages_is_bank_journal():
            self.apply_100_payment_analytic = False
            self.payment_analytic_account_id = False
        elif self.journal_id:
            self.apply_100_payment_analytic = True

    def _ages_payment_analytic_distribution(self):
        """
        Analytic distribution for the payment (credit) journal item.

        Bank journals: credit the journal account with no analytic.
        Cash/other: 100% of the selected payment analytic when enabled.
        """
        self.ensure_one()
        if self._ages_is_bank_journal():
            return False
        if self.apply_100_payment_analytic and self.payment_analytic_account_id:
            return {str(self.payment_analytic_account_id.id): 100.0}

        totals = {}
        total_amount = sum(self.line_ids.mapped('amount'))
        if total_amount <= 0:
            return False

        for line in self.line_ids:
            aa = line.analytic_account_id
            if not aa:
                continue
            totals[aa.id] = totals.get(aa.id, 0.0) + line.amount

        if not totals:
            return False

        dist = {}
        running = 0.0
        items = list(totals.items())
        for idx, (aa_id, amount) in enumerate(items):
            if idx == len(items) - 1:
                pct = round(100.0 - running, 6)
            else:
                pct = round((amount / total_amount) * 100.0, 6)
                running += pct
            if pct:
                dist[str(aa_id)] = pct
        return dist or False

    def _ages_validate_payment_liquidity_analytic(self):
        self.ensure_one()
        if self._ages_is_bank_journal():
            return
        if not self.apply_100_payment_analytic:
            raise UserError(_(
                'Enable Apply 100% Payment Analytic Distribution.'
            ))
        if not self.payment_analytic_account_id:
            raise UserError(_(
                'Select an Analytic Account for 100% payment analytic distribution.'
            ))

    def _ages_validate_lines_for_accounting(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Please add at least one expense line."))
        missing_project = self.line_ids.filtered(lambda l: not l.project_id)
        if missing_project:
            raise UserError(_("Every expense line must have a Project selected."))
        missing_analytic = self.line_ids.filtered(lambda l: not l.analytic_account_id)
        if missing_analytic:
            names = ', '.join(missing_analytic.mapped('project_id.display_name'))
            raise UserError(_(
                "These projects have no analytic account: %s"
            ) % names)
        payable_without_partner = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable' and not l.partner_id
        )
        if payable_without_partner:
            raise UserError(_(
                "Partner is required on every line whose Expense Account is a Payable account."
            ))
        for line in self.line_ids.filtered(lambda l: not l.partner_id):
            line.partner_id = self.vendor_id

    def action_confirm(self):
        for rec in self:
            if rec.state != 'new':
                raise UserError(_("Only records in 'New' state can be confirmed."))
            rec._ages_validate_lines_for_accounting()
            rec._ages_validate_payment_liquidity_analytic()
            rec.state = 'confirmed'

    def action_cancel(self):
        for rec in self:
            if rec.state != 'new':
                raise UserError(_("Only records in 'New' state can be cancelled."))
            rec.state = 'cancelled'

    def _ages_payment_vals(self):
        """Values used to create or update the linked account.payment."""
        self.ensure_one()
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.vendor_id.id,
            'amount': self.total_amount,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'memo': self._ages_payment_memo(),
            'company_id': self.company_id.id or self.env.company.id,
        }
        if 'ages_sub_company_id' in self.env['account.payment']._fields and self.sub_company_id:
            payment_vals['ages_sub_company_id'] = self.sub_company_id.id
        if 'sub_company_id' in self.env['account.payment']._fields and self.sub_company_id:
            payment_vals['sub_company_id'] = self.sub_company_id.id

        # Set project on payment only when all lines share the same project
        line_projects = self.line_ids.mapped('project_id')
        if len(line_projects) == 1:
            if 'ages_project_id' in self.env['account.payment']._fields:
                payment_vals['ages_project_id'] = line_projects.id
            if 'ages_analytic_account_id' in self.env['account.payment']._fields and line_projects[:1].account_id:
                payment_vals['ages_analytic_account_id'] = line_projects.account_id.id
        if 'ages_apply_100_payment_analytic' in self.env['account.payment']._fields:
            payment_vals['ages_apply_100_payment_analytic'] = (
                False if self._ages_is_bank_journal() else self.apply_100_payment_analytic
            )
        if (
            'ages_payment_analytic_account_id' in self.env['account.payment']._fields
            and self.payment_analytic_account_id
            and not self._ages_is_bank_journal()
        ):
            payment_vals['ages_payment_analytic_account_id'] = self.payment_analytic_account_id.id
        return payment_vals

    def _ages_payment_memo(self):
        self.ensure_one()
        voucher = self.name if self.name and self.name not in (_('New'), 'New', '/') else False
        if voucher and self.description:
            return '%s - %s' % (voucher, self.description)
        return voucher or self.description or False

    def _ages_reset_payment_to_draft(self, payment):
        """Reset a linked payment + its journal entry to draft (Odoo 18 states)."""
        if not payment:
            return
        if payment.state in ('in_process', 'paid', 'canceled', 'rejected'):
            move = payment.move_id
            if move and move.state == 'posted':
                move.line_ids.remove_move_reconcile()
            payment.action_draft()
        elif payment.move_id and payment.move_id.state == 'posted':
            payment.move_id.line_ids.remove_move_reconcile()
            payment.move_id.button_draft()

    def _ages_apply_sub_company_on_line_vals(self, line_vals, sub_company):
        if not sub_company:
            return line_vals
        if 'sub_company_id' in self.env['account.move.line']._fields:
            line_vals['sub_company_id'] = sub_company.id
        if 'ages_sub_company_id' in self.env['account.move.line']._fields:
            line_vals['ages_sub_company_id'] = sub_company.id
        return line_vals

    def _ages_rebuild_payment_move_lines(self, payment):
        """Replace payment JE lines with expense detail + cash/bank credit.

        - Expense (debit) lines: analytic distribution = that expense line's project analytic (100%).
        - Payment account (credit) line: no analytic when the payment journal
          is Bank; otherwise 100% of the selected payment analytic.
        """
        self.ensure_one()
        move = payment.move_id
        if not move:
            raise UserError(_(
                "No journal entry was created for payment %(payment)s. "
                "Check the payment journal and outstanding accounts, then try Approve again."
            ) % {'payment': payment.display_name})

        skip_ctx = {'skip_account_move_synchronization': True, 'check_move_validity': False}
        if move.state == 'posted':
            move.line_ids.remove_move_reconcile()
            move.with_context(**skip_ctx).button_draft()

        cash_account = self.journal_id.default_account_id
        if not cash_account:
            raise UserError(_("Selected payment journal '%s' has no default account.") % self.journal_id.name)

        payment_analytic_dist = self._ages_payment_analytic_distribution()
        line_commands = [Command.clear()]

        # Credit: payment / cash-bank account
        credit_line_vals = {
            'name': self._ages_payment_memo() or self.description,
            'partner_id': self.vendor_id.id,
            'account_id': cash_account.id,
            'debit': 0.0,
            'credit': self.total_amount,
            'analytic_distribution': payment_analytic_dist,
        }
        credit_line_vals = self._ages_apply_sub_company_on_line_vals(
            credit_line_vals, self.sub_company_id,
        )
        line_commands.append(Command.create(credit_line_vals))

        # Debit: selected COA + line partner + line analytic
        for exp_line in self.line_ids:
            if not exp_line.account_id:
                raise UserError(_("Every expense line must have an Account."))
            debit_line_vals = {
                'name': exp_line.name or self.description,
                'partner_id': exp_line.partner_id.id or False,
                'account_id': exp_line.account_id.id,
                'debit': exp_line.amount,
                'credit': 0.0,
                'analytic_distribution': exp_line._ages_analytic_distribution(),
            }
            debit_line_vals = self._ages_apply_sub_company_on_line_vals(
                debit_line_vals, exp_line._ages_get_sub_company(),
            )
            line_commands.append(Command.create(debit_line_vals))

        move_vals = {
            'date': self.date,
            'ref': self._ages_payment_memo() or self.description,
            'partner_id': self.vendor_id.id,
            'journal_id': self.journal_id.id,
            'line_ids': line_commands,
        }
        if 'ages_sub_company_id' in move._fields and self.sub_company_id:
            move_vals['ages_sub_company_id'] = self.sub_company_id.id

        line_projects = self.line_ids.mapped('project_id')
        if len(line_projects) == 1:
            if 'ages_project_id' in move._fields:
                move_vals['ages_project_id'] = line_projects.id
            if 'ages_analytic_account_id' in move._fields and self.analytic_account_id:
                move_vals['ages_analytic_account_id'] = self.analytic_account_id.id

        move.with_context(**skip_ctx).write(move_vals)
        if not move.line_ids.filtered(lambda line: line.display_type not in ('line_section', 'line_note')):
            raise UserError(_(
                "Could not build journal items for this expense. "
                "Check that expense accounts belong to the same company as the payment journal."
            ))
        move.with_context(**skip_ctx).action_post()

    def _ages_ensure_payment_move(self, payment):
        """Make sure the payment has a draft journal entry we can rebuild."""
        self.ensure_one()
        skip_ctx = {'skip_account_move_synchronization': True}
        payment = payment.with_context(**skip_ctx)
        if payment.move_id:
            if payment.move_id.state == 'posted':
                payment.move_id.line_ids.remove_move_reconcile()
                payment.move_id.button_draft()
            if payment.state != 'draft':
                payment.state = 'draft'
            return payment

        if not payment.outstanding_account_id:
            payment.outstanding_account_id = payment._get_outstanding_account(payment.payment_type)
        payment._generate_journal_entry()
        payment = payment.browse(payment.id)
        if not payment.move_id:
            raise UserError(_(
                "Could not create a journal entry for this expense payment. "
                "Set an outstanding payments account on the journal payment method, then try again."
            ))
        if payment.move_id.state == 'posted':
            payment.move_id.button_draft()
        if payment.state != 'draft':
            payment.state = 'draft'
        return payment

    def action_approve(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_("Only records in 'Confirmed' state can be approved."))
            rec._ages_validate_lines_for_accounting()
            rec._ages_validate_payment_liquidity_analytic()
            if rec.total_amount <= 0:
                raise UserError(_("The total amount of expenses must be greater than zero."))
            if not rec.journal_id.default_account_id:
                raise UserError(_("Selected payment journal '%s' has no default account.") % rec.journal_id.name)

            payment_vals = rec._ages_payment_vals()
            payment = rec.payment_id
            # Skip payment↔move sync: expense JEs are multi-line and rebuilt below.
            # Core _synchronize_to_moves expects a singleton counterpart line.
            pay_ctx = {'skip_account_move_synchronization': True}

            if payment:
                rec._ages_reset_payment_to_draft(payment)
                payment.with_context(**pay_ctx).write(payment_vals)
            else:
                payment = self.env['account.payment'].with_context(**pay_ctx).create(
                    payment_vals
                )

            # Build expense lines on a draft move first — never post an empty payment JE.
            payment = rec._ages_ensure_payment_move(payment)
            rec._ages_rebuild_payment_move_lines(payment)

            if payment.state == 'draft':
                # Move is already posted by rebuild; only advance payment state.
                new_state = (
                    'paid'
                    if payment.outstanding_account_id
                    and payment.outstanding_account_id.account_type == 'asset_cash'
                    else 'in_process'
                )
                payment.with_context(**pay_ctx).write({'state': new_state})
            elif payment.state == 'in_process' and payment.outstanding_account_id \
                    and payment.outstanding_account_id.account_type == 'asset_cash':
                payment.with_context(**pay_ctx).write({'state': 'paid'})

            rec.payment_id = payment.id
            rec.state = 'approved'

    def init(self):
        super().init()
        cr = self.env.cr
        cr.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'ages_expense' AND column_name = 'name'"
        )
        if not cr.fetchone():
            return
        cr.execute(
            "UPDATE ages_expense SET name = 'New' "
            "WHERE name IS NULL OR btrim(name) = ''"
        )
        cr.execute(
            "SELECT id, date FROM ages_expense "
            "WHERE name IN ('New', '/') ORDER BY id"
        )
        rows = cr.fetchall()
        sequence = self.env['ir.sequence']
        for rec_id, expense_date in rows:
            voucher = sequence.next_by_code('ages.expense', sequence_date=expense_date)
            if voucher:
                cr.execute(
                    "UPDATE ages_expense SET name = %s WHERE id = %s",
                    (voucher, rec_id),
                )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            self._ages_apply_bank_journal_vals(vals)
            if vals.get('name', _('New')) in (_('New'), 'New', False, '/'):
                date = vals.get('date') or fields.Date.context_today(self)
                vals['name'] = (
                    sequence.next_by_code('ages.expense', sequence_date=date)
                    or _('New')
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('journal_id'):
            vals = dict(vals)
            self._ages_apply_bank_journal_vals(vals)
        return super().write(vals)

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('confirmed', 'approved'):
                raise UserError(_("Reset to Draft is only allowed from Confirmed or Approved state."))
            rec._ages_reset_payment_to_draft(rec.payment_id)
            rec.state = 'new'

    def _ages_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expense'),
            'res_model': 'ages.expense',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': self.id,
            'target': 'current',
        }

    def action_view_payment(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment entry linked to this expense record."))
        return {
            'name': _('Payment Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.payment_id.id,
        }

    def unlink(self):
        for rec in self:
            if rec.state in ('confirmed', 'approved'):
                raise UserError(_("You cannot delete an expense record in '%s' state.") % rec.state.capitalize())
            if rec.payment_id:
                payment = rec.payment_id
                rec._ages_reset_payment_to_draft(payment)
                payment.unlink()
        return super().unlink()

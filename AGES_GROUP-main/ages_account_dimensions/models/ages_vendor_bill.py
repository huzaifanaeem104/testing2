# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare, float_is_zero

from .ages_vendor_bill_const import AGES_VENDOR_BILL_TYPES


class AccountMove(models.Model):
    _inherit = 'account.move'

    ages_bill_type = fields.Selection(
        selection=AGES_VENDOR_BILL_TYPES,
        string='Bill Type',
        copy=True,
        tracking=True,
        help='Normal: standard vendor bill. '
             'Subcontractor: service products only, AGES holds retention. '
             'Rental Service: bill by hour or day.',
    )
    ages_retention_percent = fields.Float(
        string='Retention %',
        copy=True,
        tracking=True,
        help='Percentage AGES holds from the certified untaxed amount.',
    )
    ages_is_retention_release = fields.Boolean(
        string='Retention Release',
        copy=False,
        default=False,
        help='This vendor bill releases retention previously held on a subcontractor bill.',
    )
    ages_retention_source_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Retention Source Bill',
        copy=False,
        index=True,
        ondelete='restrict',
        domain="[('move_type', '=', 'in_invoice'), ('ages_is_retention_release', '=', False)]",
    )
    ages_retention_release_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='ages_retention_source_move_id',
        string='Retention Releases',
    )
    ages_retention_release_count = fields.Integer(
        string='Release Count',
        compute='_compute_ages_retention_amounts',
    )
    ages_retention_held_amount = fields.Monetary(
        string='Retention Held',
        compute='_compute_ages_retention_amounts',
        currency_field='currency_id',
    )
    ages_retention_released_amount = fields.Monetary(
        string='Retention Released',
        compute='_compute_ages_retention_amounts',
        currency_field='currency_id',
    )
    ages_retention_remaining_amount = fields.Monetary(
        string='Retention Remaining',
        compute='_compute_ages_retention_amounts',
        currency_field='currency_id',
    )
    ages_show_rent_hours = fields.Boolean(
        compute='_compute_ages_rent_columns',
    )
    ages_show_rent_days = fields.Boolean(
        compute='_compute_ages_rent_columns',
    )

    @api.depends('ages_bill_type', 'invoice_line_ids.ages_rent_type', 'invoice_line_ids.display_type', 'invoice_line_ids.ages_is_vendor_retention_line')
    def _compute_ages_rent_columns(self):
        for move in self:
            rental = move.ages_bill_type == 'rental'
            types = set(move._ages_retention_product_lines().mapped('ages_rent_type'))
            types.discard(False)
            move.ages_show_rent_hours = rental and (not types or 'hour' in types)
            move.ages_show_rent_days = rental and (not types or 'day' in types)

    def _ages_vendor_bill_document(self):
        return self.filtered(lambda move: move.is_purchase_document(include_receipts=True))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move_type = res.get('move_type') or self.env.context.get('default_move_type')
        if move_type in ('in_invoice', 'in_refund', 'in_receipt') and 'ages_bill_type' in fields_list:
            res.setdefault('ages_bill_type', 'normal')
        return res

    def _ages_retention_product_lines(self):
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda line: line.display_type == 'product' and not line.ages_is_vendor_retention_line
        )

    def _ages_retention_hold_lines(self):
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda line: line.display_type == 'product' and line.ages_is_vendor_retention_line
        )

    def _ages_retention_base_amount(self):
        self.ensure_one()
        return sum(self._ages_retention_product_lines().mapped('price_subtotal'))

    def _ages_retention_account(self):
        self.ensure_one()
        return self.company_id.ages_vendor_retention_account_id

    @api.onchange('ages_bill_type')
    def _onchange_ages_bill_type(self):
        if self.ages_bill_type != 'subcontract' and not self.ages_is_retention_release:
            self.ages_retention_percent = 0.0
        if self.ages_bill_type == 'rental':
            for line in self._ages_retention_product_lines():
                if not line.ages_rent_type:
                    line.ages_rent_type = 'day'
                line._ages_apply_rent_uom()
        elif not self.ages_is_retention_release:
            for line in self._ages_retention_product_lines():
                line.ages_rent_type = False

    @api.constrains('ages_retention_percent', 'ages_bill_type', 'ages_is_retention_release')
    def _check_ages_retention_percent(self):
        for move in self._ages_vendor_bill_document():
            if move.ages_is_retention_release:
                continue
            if move.ages_bill_type != 'subcontract' and move.ages_retention_percent:
                raise ValidationError(_('Retention % applies only to Subcontractor bills.'))
            if move.ages_retention_percent < 0.0 or move.ages_retention_percent > 100.0:
                raise ValidationError(_('Retention % must be between 0 and 100.'))

    @api.depends(
        'state',
        'move_type',
        'ages_is_retention_release',
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.ages_is_vendor_retention_line',
        'ages_retention_release_ids.state',
        'ages_retention_release_ids.invoice_line_ids.price_subtotal',
        'ages_retention_release_ids.invoice_line_ids.ages_is_vendor_retention_line',
        'reversal_move_ids.state',
        'reversal_move_ids.invoice_line_ids.price_subtotal',
        'reversal_move_ids.invoice_line_ids.ages_is_vendor_retention_line',
    )
    def _compute_ages_retention_amounts(self):
        for move in self:
            releases = move.ages_retention_release_ids.filtered(lambda rec: rec.state != 'cancel')
            move.ages_retention_release_count = len(releases)
            hold_lines = move.invoice_line_ids.filtered(
                lambda line: line.display_type == 'product' and line.ages_is_vendor_retention_line
            )
            held = abs(sum(hold_lines.mapped('price_subtotal')))
            released = 0.0
            for release in releases.filtered(lambda rec: rec.state == 'posted'):
                release_lines = release.invoice_line_ids.filtered(
                    lambda line: line.display_type == 'product' and line.ages_is_vendor_retention_line
                )
                released += abs(sum(release_lines.mapped('price_subtotal')))
            for reversal in move.reversal_move_ids.filtered(lambda rec: rec.state == 'posted'):
                reversal_lines = reversal.invoice_line_ids.filtered(
                    lambda line: line.display_type == 'product' and line.ages_is_vendor_retention_line
                )
                released += abs(sum(reversal_lines.mapped('price_subtotal')))
            if move.ages_is_retention_release or move.move_type not in ('in_invoice', 'in_refund'):
                move.ages_retention_held_amount = 0.0
                move.ages_retention_released_amount = 0.0
                move.ages_retention_remaining_amount = 0.0
                continue
            move.ages_retention_held_amount = held
            move.ages_retention_released_amount = released
            remaining = held - released
            if float_compare(remaining, 0.0, precision_rounding=move.currency_id.rounding) < 0:
                remaining = 0.0
            move.ages_retention_remaining_amount = remaining

    def _ages_retention_line_vals(self, amount):
        self.ensure_one()
        account = self._ages_retention_account()
        dist = False
        if hasattr(self, '_ages_analytic_distribution'):
            dist = self._ages_analytic_distribution()
        sign = -1.0 if self.move_type == 'in_invoice' else 1.0
        if self.ages_is_retention_release:
            sign = 1.0 if self.move_type == 'in_invoice' else -1.0
        name = (
            _('Retention release of %s') % (self.ages_retention_source_move_id.name or '')
            if self.ages_is_retention_release
            else _('Retention held (%.2f%%) — AGES holding') % (self.ages_retention_percent or 0.0)
        )
        return {
            'display_type': 'product',
            'name': name,
            'quantity': 1.0,
            'price_unit': sign * amount,
            'discount': 0.0,
            'account_id': account.id,
            'tax_ids': [Command.clear()],
            'product_id': False,
            'ages_is_vendor_retention_line': True,
            'analytic_distribution': dist or False,
        }

    def _ages_sync_vendor_retention_line(self):
        if self.env.context.get('ages_syncing_vendor_retention'):
            return
        moves = self._ages_vendor_bill_document().filtered(lambda move: move.state == 'draft')
        for move in moves:
            hold_lines = move._ages_retention_hold_lines()
            if move.ages_is_retention_release:
                continue
            apply = (
                move.ages_bill_type == 'subcontract'
                and move.ages_retention_percent
                and move._ages_retention_product_lines()
            )
            if not apply:
                if hold_lines:
                    hold_lines.with_context(
                        ages_syncing_vendor_retention=True,
                        dynamic_unlink=True,
                    ).unlink()
                continue
            account = move._ages_retention_account()
            if not account:
                continue
            base = move._ages_retention_base_amount()
            amount = move.currency_id.round(abs(base) * move.ages_retention_percent / 100.0)
            if float_is_zero(amount, precision_rounding=move.currency_id.rounding):
                if hold_lines:
                    hold_lines.with_context(
                        ages_syncing_vendor_retention=True,
                        dynamic_unlink=True,
                    ).unlink()
                continue
            vals = move._ages_retention_line_vals(amount)
            max_seq = max(move.invoice_line_ids.mapped('sequence') or [10])
            vals['sequence'] = max_seq + 10
            move = move.with_context(ages_syncing_vendor_retention=True)
            if hold_lines:
                hold_lines[0].with_context(ages_syncing_vendor_retention=True).write(vals)
                extra = hold_lines - hold_lines[0]
                if extra:
                    extra.with_context(
                        ages_syncing_vendor_retention=True,
                        dynamic_unlink=True,
                    ).unlink()
            else:
                move.write({'invoice_line_ids': [Command.create(vals)]})

    def _ages_validate_vendor_bill_type(self):
        for move in self._ages_vendor_bill_document():
            if move.ages_is_retention_release:
                if not move.ages_retention_source_move_id:
                    raise UserError(_('A retention release bill must be linked to the original vendor bill.'))
                hold_lines = move._ages_retention_hold_lines()
                if not hold_lines:
                    raise UserError(_('The retention release bill is missing the retention payable line.'))
                continue
            lines = move._ages_retention_product_lines()
            if move.ages_bill_type in ('subcontract', 'rental'):
                goods = lines.filtered(lambda line: line.product_id and line.product_id.type != 'service')
                if goods:
                    raise UserError(_(
                        'Bill type "%s" only allows service products. Remove or replace: %s'
                    ) % (
                        dict(move._fields['ages_bill_type'].selection).get(move.ages_bill_type),
                        ', '.join(goods.mapped('product_id.display_name')),
                    ))
            if move.ages_bill_type == 'rental':
                missing = lines.filtered(lambda line: not line.ages_rent_type)
                if missing:
                    raise UserError(_('Set Rent Type (Per Hour or Per Day) on every rental line.'))
                zero = lines.filtered(lambda line: line.quantity <= 0)
                if zero:
                    raise UserError(_('Enter Hours or Days on every rental line so the amount can be calculated.'))
            if move.ages_bill_type == 'subcontract' and move.ages_retention_percent:
                if not move._ages_retention_account():
                    raise UserError(_(
                        'Configure Vendor Retention Payable in '
                        'Project → Configuration → Settings (e.g. 201003 RETENTION MONEY PAYABLES).'
                    ))
                hold_lines = move._ages_retention_hold_lines()
                if not hold_lines:
                    raise UserError(_(
                        'Subcontractor bill %s is missing the retention hold line. '
                        'Set Retention %% and save before confirming.'
                    ) % move.display_name)

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._ages_sync_vendor_retention_line()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('ages_syncing_vendor_retention'):
            return res
        sync_fields = {
            'ages_bill_type', 'ages_retention_percent', 'invoice_line_ids',
            'ages_is_retention_release', 'ages_analytic_account_id',
        }
        if sync_fields.intersection(vals):
            self._ages_sync_vendor_retention_line()
        return res

    def _ages_reconcile_vendor_retention_release(self):
        """Match the release debit on 201003 with the original hold credit.

        That clearing is not a vendor payment. Pay only the release bill's
        vendor payable residual.
        """
        for move in self.filtered(
            lambda rec: rec.state == 'posted' and rec.ages_is_retention_release
        ):
            source = move.ages_retention_source_move_id
            if not source:
                continue
            hold = source.line_ids.filtered(
                lambda line: line.ages_is_vendor_retention_line and not line.reconciled
            )
            release = move.line_ids.filtered(
                lambda line: line.ages_is_vendor_retention_line and not line.reconciled
            )
            to_reconcile = hold | release
            if len(to_reconcile) < 2 or len(to_reconcile.account_id) != 1:
                continue
            to_reconcile.reconcile()

    def _compute_payments_widget_to_reconcile_info(self):
        super()._compute_payments_widget_to_reconcile_info()
        for move in self:
            widget = move.invoice_outstanding_credits_debits_widget
            content = widget.get('content') if widget else False
            if not content:
                continue
            line_ids = [item['id'] for item in content if item.get('id')]
            if not line_ids:
                continue
            lines = self.env['account.move.line'].browse(line_ids)
            retention_account = move.company_id.ages_vendor_retention_account_id
            skip_ids = set(lines.filtered(
                lambda line: line.ages_is_vendor_retention_line
                or (retention_account and line.account_id == retention_account)
            ).ids)
            if not skip_ids:
                continue
            kept = [item for item in content if item.get('id') not in skip_ids]
            if kept:
                move.invoice_outstanding_credits_debits_widget = dict(widget, content=kept)
                move.invoice_has_outstanding = True
            else:
                move.invoice_outstanding_credits_debits_widget = False
                move.invoice_has_outstanding = False

    def action_post(self):
        self._ages_sync_vendor_retention_line()
        self._ages_validate_vendor_bill_type()
        res = super().action_post()
        self._ages_reconcile_vendor_retention_release()
        return res

    def _compute_show_reset_to_draft_button(self):
        """Keep Reset to Draft on vendor bills even when stock valuation layers exist.

        `stock_account` hides the button whenever bill lines have price-difference
        SVLs (typical for a posted PO bill of storable products). The bill and its
        journal entry are the same `account.move`; users must be able to draft,
        edit invoice lines, and confirm again so the JE is rebuilt and posted.
        Hash / restrict / cancel-request rules from core still apply.
        """
        super()._compute_show_reset_to_draft_button()
        for move in self:
            if not move.is_purchase_document(include_receipts=True):
                continue
            if move.inalterable_hash or self._is_move_restricted(move):
                continue
            if move.state == 'cancel' or (move.state == 'posted' and not move.need_cancel_request):
                move.show_reset_to_draft_button = True

    def _ages_unlink_vendor_bill_price_difference_layers(self):
        """Drop bill-owned price-difference SVLs so Confirm can recreate them."""
        if 'stock.valuation.layer' not in self.env:
            return
        layers = self.env['stock.valuation.layer'].sudo().search([
            ('account_move_line_id', 'in', self.line_ids.ids),
        ])
        if not layers:
            return
        for layer in layers:
            parent = layer.stock_valuation_layer_id
            if parent:
                parent.remaining_value -= layer.value
        extra_moves = (layers.mapped('account_move_id') - self).filtered(
            lambda move: (
                move.move_type == 'entry'
                and move.stock_valuation_layer_ids
                and not (move.stock_valuation_layer_ids - layers)
            )
        )
        if extra_moves:
            extra_moves.with_context(skip_invoice_sync=True).button_draft()
            extra_moves.unlink()
        layers.unlink()

    def button_draft(self):
        blocked = self.filtered(
            lambda move: move.ages_retention_release_ids.filtered(lambda rec: rec.state != 'cancel')
        )
        if blocked:
            raise UserError(_(
                'Cannot reset %s to draft while retention release bills exist. '
                'Cancel or reset those releases first.'
            ) % ', '.join(blocked.mapped('name')))
        bills = self.filtered(lambda move: move.is_purchase_document(include_receipts=True))
        if bills:
            bills._ages_unlink_vendor_bill_price_difference_layers()
        return super().button_draft()

    def action_ages_reset_vendor_bill_draft(self):
        """Header fallback when stock_account keeps the core Reset button hidden."""
        return self.button_draft()

    def action_ages_open_journal_entry(self):
        """Open this bill's journal items (the bill record is the journal entry)."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all_a')
        action['name'] = _('Journal Entry')
        action['domain'] = [('move_id', '=', self.id)]
        action['context'] = {
            'create': False,
            'delete': False,
            'search_default_posted': 0,
        }
        return action

    def button_cancel(self):
        blocked = self.filtered(
            lambda move: move.ages_retention_release_ids.filtered(lambda rec: rec.state != 'cancel')
        )
        if blocked:
            raise UserError(_(
                'Cannot cancel %s while retention release bills exist. '
                'Cancel those releases first.'
            ) % ', '.join(blocked.mapped('name')))
        return super().button_cancel()

    def action_ages_open_retention_release_wizard(self):
        self.ensure_one()
        if self.state != 'posted' or self.move_type != 'in_invoice' or self.ages_is_retention_release:
            raise UserError(_('Retention can only be released from a posted subcontractor vendor bill.'))
        if float_compare(
            self.ages_retention_remaining_amount, 0.0,
            precision_rounding=self.currency_id.rounding,
        ) <= 0:
            raise UserError(_('There is no remaining retention to release on this bill.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Release Retention'),
            'res_model': 'ages.vendor.retention.release.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_amount': self.ages_retention_remaining_amount,
            },
        }

    def action_view_ages_retention_releases(self):
        self.ensure_one()
        releases = self.ages_retention_release_ids
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_in_invoice_type')
        action['domain'] = [('id', 'in', releases.ids)]
        if len(releases) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = releases.id
        return action

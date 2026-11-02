# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class AgesMobilizationAdvance(models.Model):
    _inherit = 'ages.mobilization.advance'

    payment_ids = fields.One2many(
        comodel_name='account.payment',
        inverse_name='ages_mobilization_advance_id',
        string='Payments',
        copy=False,
    )
    payment_count = fields.Integer(
        string='Payment Count',
        compute='_compute_payment_status',
    )
    amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_payment_status',
        currency_field='currency_id',
    )
    amount_remaining = fields.Monetary(
        string='Amount Remaining',
        compute='_compute_payment_status',
        currency_field='currency_id',
    )
    payment_state = fields.Selection(
        selection=[
            ('not_paid', 'Not Paid'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid'),
        ],
        string='Payment Status',
        compute='_compute_payment_status',
        store=True,
    )
    ages_wth_amount_display = fields.Char(
        string='WHT Amount (Rs)',
        compute='_compute_ages_wth_amount_display',
        help='Document WHT Amount / WHT already posted on payments.',
    )
    ages_wth_amount_posted = fields.Monetary(
        string='WHT Posted',
        compute='_compute_ages_wth_amount_display',
        currency_field='currency_id',
    )
    ages_wth_amount_remaining = fields.Monetary(
        string='WHT Remaining',
        compute='_compute_ages_wth_amount_display',
        currency_field='currency_id',
    )

    def _ages_format_wht_pair(self, total_amount, posted_amount):
        def _fmt(amount):
            amount = abs(amount or 0.0)
            if abs(amount - round(amount)) < 0.005:
                return '%d' % int(round(amount))
            return '%.2f' % amount
        return '%s/%s' % (_fmt(total_amount), _fmt(posted_amount))

    def _ages_get_posted_payments(self):
        self.ensure_one()
        return self.payment_ids.filtered(
            lambda payment: payment.state in ('in_process', 'paid')
        )

    def _ages_sum_posted_withholding(self, payments=None, taxes=None):
        self.ensure_one()
        payments = payments if payments is not None else self._ages_get_posted_payments()
        taxes = taxes if taxes is not None else self.wth_tax_id
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
        'wht_on_mobilization',
        'wth_amount',
        'wth_tax_id',
        'currency_id',
        'payment_ids',
        'payment_ids.state',
        'payment_ids.withholding_line_ids.amount',
        'payment_ids.withholding_line_ids.tax_id',
    )
    def _compute_ages_wth_amount_display(self):
        for rec in self:
            total = abs(rec.wth_amount or 0.0) if rec.wht_on_mobilization else 0.0
            posted = rec._ages_sum_posted_withholding() if rec.wht_on_mobilization else 0.0
            remaining = max(total - posted, 0.0)
            rec.ages_wth_amount_posted = posted
            rec.ages_wth_amount_remaining = remaining
            rec.ages_wth_amount_display = (
                rec._ages_format_wht_pair(total, posted) if rec.wht_on_mobilization else False
            )

    @api.depends(
        'mobilization_amount',
        'currency_id',
        'payment_ids',
        'payment_ids.state',
        'payment_ids.amount',
        'payment_ids.currency_id',
    )
    def _compute_payment_status(self):
        for rec in self:
            # Odoo 18 payment states: draft, in_process, paid, canceled, rejected
            payments = rec.payment_ids.filtered(
                lambda p: p.state not in ('draft', 'canceled', 'rejected', 'cancel')
            )
            amount_paid = 0.0
            for payment in payments:
                amount_paid += payment.currency_id._convert(
                    payment.amount,
                    rec.currency_id,
                    rec.company_id,
                    payment.date or fields.Date.context_today(rec),
                )
            total = rec.mobilization_amount or 0.0
            rounding = rec.currency_id.rounding or 0.01
            remaining = max(total - amount_paid, 0.0)
            rec.payment_count = len(payments)
            rec.amount_paid = amount_paid
            rec.amount_remaining = remaining
            if float_is_zero(amount_paid, precision_rounding=rounding):
                rec.payment_state = 'not_paid'
            elif float_compare(amount_paid, total, precision_rounding=rounding) >= 0:
                rec.payment_state = 'paid'
            else:
                rec.payment_state = 'partial'

    def _ages_get_payment_counterpart_account(self):
        self.ensure_one()
        return self.company_id.ages_mobilization_account_id

    def action_confirm(self):
        super().action_confirm()
        return self[:1].action_register_payment()

    def action_register_payment(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only Confirmed Mobilization Received can register payments.'))
        if self.payment_state == 'paid':
            raise UserError(_('This Mobilization Received is already fully paid.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Receive Mobilization Payment'),
            'res_model': 'ages.mob.retention.payment.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_ages_mobilization_advance_id': self.id,
            },
        }

    def action_view_payments(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('ages_mobilization_advance_id', '=', self.id)],
            'context': {
                'default_ages_mobilization_advance_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
            },
        }
        if self.payment_count == 1:
            action.update({
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': self.payment_ids[:1].id,
            })
        return action

    def action_reset(self):
        for rec in self:
            posted = rec.payment_ids.filtered(
                lambda p: p.state not in ('draft', 'canceled', 'rejected', 'cancel')
            )
            if posted:
                raise UserError(_(
                    'You cannot reset %s because it has posted payments. '
                    'Cancel or reverse those payments first.'
                ) % rec.display_name)
        return super().action_reset()


class AgesRetentionRecovery(models.Model):
    _inherit = 'ages.retention.recovery'

    payment_ids = fields.One2many(
        comodel_name='account.payment',
        inverse_name='ages_retention_recovery_id',
        string='Payments',
        copy=False,
    )
    payment_count = fields.Integer(
        string='Payment Count',
        compute='_compute_payment_status',
    )
    amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_payment_status',
        currency_field='currency_id',
    )
    amount_remaining = fields.Monetary(
        string='Amount Remaining',
        compute='_compute_payment_status',
        currency_field='currency_id',
    )
    payment_state = fields.Selection(
        selection=[
            ('not_paid', 'Not Paid'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid'),
        ],
        string='Payment Status',
        compute='_compute_payment_status',
        store=True,
    )
    ages_wth_amount_display = fields.Char(
        string='WHT Amount (Rs)',
        compute='_compute_ages_wth_amount_display',
        help='Document WHT Amount / WHT already posted on payments.',
    )
    ages_wth_amount_posted = fields.Monetary(
        string='WHT Posted',
        compute='_compute_ages_wth_amount_display',
        currency_field='currency_id',
    )
    ages_wth_amount_remaining = fields.Monetary(
        string='WHT Remaining',
        compute='_compute_ages_wth_amount_display',
        currency_field='currency_id',
    )

    def _ages_format_wht_pair(self, total_amount, posted_amount):
        def _fmt(amount):
            amount = abs(amount or 0.0)
            if abs(amount - round(amount)) < 0.005:
                return '%d' % int(round(amount))
            return '%.2f' % amount
        return '%s/%s' % (_fmt(total_amount), _fmt(posted_amount))

    def _ages_get_posted_payments(self):
        self.ensure_one()
        return self.payment_ids.filtered(
            lambda payment: payment.state in ('in_process', 'paid')
        )

    def _ages_sum_posted_withholding(self, payments=None, taxes=None):
        self.ensure_one()
        payments = payments if payments is not None else self._ages_get_posted_payments()
        taxes = taxes if taxes is not None else self.wth_tax_id
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
        'wht_on_retention',
        'wth_amount',
        'wth_tax_id',
        'currency_id',
        'payment_ids',
        'payment_ids.state',
        'payment_ids.withholding_line_ids.amount',
        'payment_ids.withholding_line_ids.tax_id',
    )
    def _compute_ages_wth_amount_display(self):
        for rec in self:
            total = abs(rec.wth_amount or 0.0) if rec.wht_on_retention else 0.0
            posted = rec._ages_sum_posted_withholding() if rec.wht_on_retention else 0.0
            remaining = max(total - posted, 0.0)
            rec.ages_wth_amount_posted = posted
            rec.ages_wth_amount_remaining = remaining
            rec.ages_wth_amount_display = (
                rec._ages_format_wht_pair(total, posted) if rec.wht_on_retention else False
            )

    @api.depends(
        'retention_amount',
        'currency_id',
        'payment_ids',
        'payment_ids.state',
        'payment_ids.amount',
        'payment_ids.currency_id',
    )
    def _compute_payment_status(self):
        for rec in self:
            payments = rec.payment_ids.filtered(
                lambda p: p.state not in ('draft', 'canceled', 'rejected', 'cancel')
            )
            amount_paid = 0.0
            for payment in payments:
                amount_paid += payment.currency_id._convert(
                    payment.amount,
                    rec.currency_id,
                    rec.company_id,
                    payment.date or fields.Date.context_today(rec),
                )
            total = rec.retention_amount or 0.0
            rounding = rec.currency_id.rounding or 0.01
            remaining = max(total - amount_paid, 0.0)
            rec.payment_count = len(payments)
            rec.amount_paid = amount_paid
            rec.amount_remaining = remaining
            if float_is_zero(amount_paid, precision_rounding=rounding):
                rec.payment_state = 'not_paid'
            elif float_compare(amount_paid, total, precision_rounding=rounding) >= 0:
                rec.payment_state = 'paid'
            else:
                rec.payment_state = 'partial'

    def _ages_get_payment_counterpart_account(self):
        self.ensure_one()
        return self.company_id.ages_retention_account_id

    def action_confirm(self):
        super().action_confirm()
        return self[:1].action_register_payment()

    def action_register_payment(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only Confirmed Retention Recovery can register payments.'))
        if self.payment_state == 'paid':
            raise UserError(_('This Retention Recovery is already fully paid.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Receive Retention Payment'),
            'res_model': 'ages.mob.retention.payment.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_ages_retention_recovery_id': self.id,
            },
        }

    def action_view_payments(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('ages_retention_recovery_id', '=', self.id)],
            'context': {
                'default_ages_retention_recovery_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
            },
        }
        if self.payment_count == 1:
            action.update({
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': self.payment_ids[:1].id,
            })
        return action

    def action_reset(self):
        for rec in self:
            posted = rec.payment_ids.filtered(
                lambda p: p.state not in ('draft', 'canceled', 'rejected', 'cancel')
            )
            if posted:
                raise UserError(_(
                    'You cannot reset %s because it has posted payments. '
                    'Cancel or reverse those payments first.'
                ) % rec.display_name)
        return super().action_reset()

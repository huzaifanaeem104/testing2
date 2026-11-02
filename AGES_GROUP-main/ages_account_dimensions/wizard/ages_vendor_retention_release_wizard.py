# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare


class AgesVendorRetentionReleaseWizard(models.TransientModel):
    _name = 'ages.vendor.retention.release.wizard'
    _description = 'Release Vendor Retention'

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        required=True,
        ondelete='cascade',
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('ages_is_retention_release', '=', False)]",
    )
    partner_id = fields.Many2one(
        related='move_id.partner_id',
        string='Vendor',
        readonly=True,
    )
    company_id = fields.Many2one(
        related='move_id.company_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
        readonly=True,
    )
    ages_project_id = fields.Many2one(
        related='move_id.ages_project_id',
        readonly=True,
    )
    held_amount = fields.Monetary(
        related='move_id.ages_retention_held_amount',
        string='Held',
        readonly=True,
        currency_field='currency_id',
    )
    released_amount = fields.Monetary(
        related='move_id.ages_retention_released_amount',
        string='Already Released',
        readonly=True,
        currency_field='currency_id',
    )
    remaining_amount = fields.Monetary(
        related='move_id.ages_retention_remaining_amount',
        string='Remaining',
        readonly=True,
        currency_field='currency_id',
    )
    date = fields.Date(
        string='Release Date',
        required=True,
        default=fields.Date.context_today,
    )
    amount = fields.Monetary(
        string='Amount to Release',
        required=True,
        currency_field='currency_id',
    )

    @api.onchange('move_id')
    def _onchange_move_id(self):
        if self.move_id:
            self.amount = self.move_id.ages_retention_remaining_amount

    def action_create_release_bill(self):
        self.ensure_one()
        source = self.move_id
        if source.state != 'posted' or source.ages_is_retention_release:
            raise UserError(_('Retention can only be released from a posted subcontractor vendor bill.'))
        rounding = source.currency_id.rounding
        if float_compare(self.amount, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_('Release amount must be greater than zero.'))
        if float_compare(self.amount, source.ages_retention_remaining_amount, precision_rounding=rounding) > 0:
            raise UserError(_(
                'Cannot release %(amount)s. Remaining retention on %(bill)s is %(remaining)s.'
            ) % {
                'amount': self.amount,
                'bill': source.display_name,
                'remaining': source.ages_retention_remaining_amount,
            })
        account = source._ages_retention_account()
        if not account:
            raise UserError(_(
                'Configure Vendor Retention Payable in '
                'Project → Configuration → Settings (e.g. 201003 RETENTION MONEY PAYABLES).'
            ))

        dist = False
        if hasattr(source, '_ages_analytic_distribution'):
            dist = source._ages_analytic_distribution()
        line_vals = {
            'display_type': 'product',
            'name': _('Retention release of %s') % source.name,
            'quantity': 1.0,
            'price_unit': self.amount,
            'account_id': account.id,
            'tax_ids': [Command.clear()],
            'ages_is_vendor_retention_line': True,
            'analytic_distribution': dist or False,
        }
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': source.partner_id.id,
            'invoice_date': self.date,
            'date': self.date,
            'journal_id': source.journal_id.id,
            'company_id': source.company_id.id,
            'currency_id': source.currency_id.id,
            'invoice_origin': source.name,
            'ref': _('Retention release of %s') % source.name,
            'ages_bill_type': 'subcontract',
            'ages_retention_percent': 0.0,
            'ages_is_retention_release': True,
            'ages_retention_source_move_id': source.id,
            'invoice_line_ids': [Command.create(line_vals)],
        }
        for fname in (
            'ages_project_id', 'ages_analytic_account_id',
            'ages_contract_id', 'ages_sub_company_id',
        ):
            if fname in source._fields and source[fname]:
                bill_vals[fname] = source[fname].id

        bill = self.env['account.move'].with_company(source.company_id).with_context(
            ages_syncing_vendor_retention=True,
        ).create(bill_vals)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retention Release'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.tools.float_utils import float_compare, float_is_zero


AGES_WITHHELD_SALES_TAX_REF = 'AGES-SRB-WHT:%s'


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _ages_withheld_sales_tax_refund_ref(self):
        self.ensure_one()
        return AGES_WITHHELD_SALES_TAX_REF % self.id

    def _ages_existing_withheld_sales_tax_refund(self):
        self.ensure_one()
        return self.search([
            ('move_type', '=', 'out_refund'),
            ('reversed_entry_id', '=', self.id),
            ('ref', '=', self._ages_withheld_sales_tax_refund_ref()),
            ('state', '!=', 'cancel'),
        ], limit=1)

    def _ages_clear_withheld_sales_tax(self):
        refunds = self.env['account.move']
        for invoice in self:
            refunds |= invoice._ages_clear_withheld_sales_tax_invoice()
        return refunds

    def _ages_clear_withheld_sales_tax_invoice(self):
        """No-op: RA invoices book SRB credit 100% and debit the WTH share."""
        self.ensure_one()
        return self.env['account.move']

    @api.model
    def _ages_clear_withheld_sales_tax_on_running_bills(self):
        return self.env['account.move']

    @api.model
    def _ages_cancel_withheld_sales_tax_refunds(self):
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

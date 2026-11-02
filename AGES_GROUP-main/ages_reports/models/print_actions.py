# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_print_bill(self):
        bills = self.filtered(lambda move: move.is_purchase_document(include_receipts=True))
        if not bills:
            raise UserError(_('Print Bill is only available on vendor bills.'))
        return self.env.ref('ages_reports.action_report_vendor_bill').report_action(bills)

    def action_print_journal_entry(self):
        return self.env.ref('ages_reports.action_report_journal_entry').report_action(self)

    def action_print_journal_items(self):
        lines = self.mapped('line_ids').filtered(
            lambda line: line.display_type not in ('line_section', 'line_note')
        )
        return self.env.ref('ages_reports.action_report_journal_item').report_action(lines)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def action_print_journal_items(self):
        lines = self.filtered(lambda line: line.display_type not in ('line_section', 'line_note'))
        if not lines:
            lines = self
        return self.env.ref('ages_reports.action_report_journal_item').report_action(lines)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_print_payment(self):
        return self.env.ref('ages_reports.action_report_payment').report_action(self)


class AgesExpense(models.Model):
    _inherit = 'ages.expense'

    def action_print_expense(self):
        return self.env.ref('ages_reports.action_report_expense').report_action(self)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_print_rfq(self):
        return self.env.ref('ages_reports.action_report_rfq').report_action(self)

    def action_print_po(self):
        return self.env.ref('ages_reports.action_report_po').report_action(self)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_print_receipt(self):
        return self.env.ref('ages_reports.action_report_receipt').report_action(self)

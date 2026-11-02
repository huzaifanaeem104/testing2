# -*- coding: utf-8 -*-

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVendorBillResetJournalEntry(AccountTestInvoicingCommon):

    def _create_vendor_bill(self, price_unit=100.0, post=True):
        expense = self.company_data['default_account_expense']
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-09-24',
            'invoice_line_ids': [(0, 0, {
                'name': 'Vendor bill line',
                'quantity': 1,
                'price_unit': price_unit,
                'account_id': expense.id,
            })],
        })
        if post:
            bill.action_post()
        return bill

    def test_posted_vendor_bill_shows_reset_to_draft(self):
        bill = self._create_vendor_bill()
        self.assertEqual(bill.state, 'posted')
        self.assertTrue(bill.show_reset_to_draft_button)

    def test_reset_edit_and_confirm_updates_journal_entry(self):
        bill = self._create_vendor_bill(price_unit=100.0)
        original_line_ids = set(bill.line_ids.ids)
        bill.button_draft()
        self.assertEqual(bill.state, 'draft')

        bill.invoice_line_ids[0].price_unit = 175.0
        bill.action_post()

        self.assertEqual(bill.state, 'posted')
        self.assertAlmostEqual(bill.amount_untaxed, 175.0)
        self.assertTrue(bill.line_ids)
        self.assertTrue(
            any(abs(line.balance) == 175.0 for line in bill.line_ids),
            'Confirm should rebuild posted journal items from the edited bill lines',
        )
        self.assertTrue(original_line_ids)

    def test_open_journal_entry_action_lists_this_bill_items(self):
        bill = self._create_vendor_bill()
        action = bill.action_ages_open_journal_entry()
        self.assertEqual(action['res_model'], 'account.move.line')
        self.assertEqual(action['name'], 'Journal Entry')
        self.assertIn(('move_id', '=', bill.id), action['domain'])
        self.assertFalse(action['context'].get('create'))

    def test_fallback_reset_action_drafts_posted_bill(self):
        bill = self._create_vendor_bill()
        bill.action_ages_reset_vendor_bill_draft()
        self.assertEqual(bill.state, 'draft')

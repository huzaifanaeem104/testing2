# -*- coding: utf-8 -*-

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

from ..report.general_ledger_engine import GeneralLedgerEngine
from ..report.partner_ledger_engine import PartnerLedgerEngine


@tagged('post_install', '-at_install')
class TestLedgerBatch(AccountTestInvoicingCommon):

    @classmethod
    def setup_independent_user(cls):
        return None

    def setUp(self):
        super().setUp()
        self.receivable = self.company_data['default_account_receivable']
        self.revenue = self.company_data['default_account_revenue']
        self.partner_one = self.env['res.partner'].create({'name': 'Batch Ledger One'})
        self.partner_two = self.env['res.partner'].create({'name': 'Batch Ledger Two'})
        self._create_invoice(self.partner_one, 150.0, '2026-02-10')
        self._create_invoice(self.partner_two, 80.0, '2026-03-05')

    def _create_invoice(self, partner, amount, invoice_date):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [Command.create({
                'name': 'Batch work',
                'quantity': 1,
                'price_unit': amount,
                'account_id': self.revenue.id,
            })],
        })
        move.action_post()
        return move

    def _partner_options(self, unfold_all=False):
        return {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'account_filters': ['receivable'],
            'unfold_all': unfold_all,
        }

    def _gl_options(self, unfold_all=False):
        return {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'account_ids': [self.receivable.id],
            'unfold_all': unfold_all,
        }

    def test_partner_ledger_folded_matches_unfolded_totals(self):
        folded = PartnerLedgerEngine(self.env, self._partner_options(False)).get_report_data()
        unfolded = PartnerLedgerEngine(self.env, self._partner_options(True)).get_report_data()
        folded_partners = {
            line['partner_id']: (line['debit'], line['credit'], line['balance'])
            for line in folded['lines']
            if line['line_type'] == 'partner'
        }
        unfolded_partners = {
            line['partner_id']: (line['debit'], line['credit'], line['balance'])
            for line in unfolded['lines']
            if line['line_type'] == 'partner'
        }
        self.assertEqual(folded_partners, unfolded_partners)
        one = next(
            line for line in unfolded['lines']
            if line.get('partner_id') == self.partner_one.id
        )
        self.assertTrue(one['children'])
        self.assertGreaterEqual(len(one['children']), 2)
        detail = PartnerLedgerEngine(self.env, self._partner_options(False)).get_partner_detail(
            self.partner_one.id
        )
        self.assertEqual(
            [child['id'] for child in one['children']],
            [child['id'] for child in detail['children']],
        )

    def test_general_ledger_folded_matches_unfolded_totals(self):
        folded = GeneralLedgerEngine(self.env, self._gl_options(False)).get_report_data()
        unfolded = GeneralLedgerEngine(self.env, self._gl_options(True)).get_report_data()
        folded_accounts = {
            line['account_id']: (line['debit'], line['credit'], line['balance'])
            for line in folded['lines']
            if line['line_type'] == 'account'
        }
        unfolded_accounts = {
            line['account_id']: (line['debit'], line['credit'], line['balance'])
            for line in unfolded['lines']
            if line['line_type'] == 'account'
        }
        self.assertEqual(folded_accounts, unfolded_accounts)
        account_line = next(
            line for line in unfolded['lines']
            if line.get('account_id') == self.receivable.id
        )
        self.assertTrue(account_line['children'])
        detail = GeneralLedgerEngine(self.env, self._gl_options(False)).get_account_detail(
            self.receivable.id
        )
        self.assertEqual(
            [child['id'] for child in account_line['children']],
            [child['id'] for child in detail['children']],
        )

# -*- coding: utf-8 -*-

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.ages_custom_reports.report.partner_ledger_engine import PartnerLedgerEngine
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPartnerLedgerWhtSplit(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.withholding_tax_base_account_id:
            company.withholding_tax_base_account_id = cls.company_data['default_account_assets'].id
        cls.wht_tax = cls.env['account.tax'].create({
            'name': 'WH TAX -7.5% Ledger',
            'amount': -7.5,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'is_withholding_tax_on_payment': True,
            'company_id': company.id,
        })
        receivable = cls.company_data['default_account_receivable']
        income = cls.company_data['default_account_revenue']
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': '2026-09-20',
            'invoice_line_ids': [(0, 0, {
                'name': 'Work',
                'quantity': 1,
                'price_unit': 4626675.0,
                'account_id': income.id,
            })],
        })
        cls.invoice.action_post()
        bank = cls.company_data['default_journal_bank']
        cls.payment = cls.env['account.payment'].with_context(
            ages_skip_journal_sequence=True,
        ).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': cls.partner_a.id,
            'amount': 4626675.0,
            'date': '2026-09-21',
            'journal_id': bank.id,
            'destination_account_id': receivable.id,
            'should_withhold_tax': True,
        })
        cls.env['account.payment.withholding.line'].create({
            'payment_id': cls.payment.id,
            'name': cls.wht_tax.name,
            'tax_id': cls.wht_tax.id,
            'account_id': company.withholding_tax_base_account_id.id,
            'placeholder_type': 'not_defined',
            'source_base_amount_currency': 4626675.0,
            'source_base_amount': 4626675.0,
            'source_tax_amount_currency': 347000.63,
            'source_tax_amount': 347000.63,
            'base_amount': 4626675.0,
            'amount': 347000.63,
        })
        cls.payment.should_withhold_tax = True
        if not cls.payment.move_id:
            cls.payment._generate_journal_entry()
        if cls.payment.move_id.state == 'draft':
            cls.payment.move_id.action_post()

    def _engine(self):
        return PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner_a.id],
            'account_filters': ['receivable'],
            'unfold_all': True,
        })

    def test_payment_row_splits_net_and_wht(self):
        data = self._engine().get_report_data()
        partner_line = next(
            line for line in data['lines']
            if line.get('partner_id') == self.partner_a.id
        )
        payment_rows = [
            child for child in partner_line['children']
            if child.get('move_id') == self.payment.move_id.id
        ]
        self.assertEqual(len(payment_rows), 2)
        net_row, tax_row = payment_rows
        gross = 4626675.0
        tax = 347000.63
        net = self.env.company.currency_id.round(gross - tax)
        self.assertAlmostEqual(net_row['credit'], net, places=2)
        self.assertAlmostEqual(tax_row['credit'], tax, places=2)
        self.assertAlmostEqual(net_row['credit'] + tax_row['credit'], gross, places=2)
        self.assertEqual(tax_row.get('badge'), 'WHT')
        self.assertFalse(net_row.get('badge'))
        self.assertEqual(tax_row.get('communication'), net_row.get('communication'))
        self.assertNotIn(' — 0', tax_row.get('communication') or '')

    def test_invoice_row_stays_single_line(self):
        data = self._engine().get_report_data()
        partner_line = next(
            line for line in data['lines']
            if line.get('partner_id') == self.partner_a.id
        )
        invoice_rows = [
            child for child in partner_line['children']
            if child.get('move_id') == self.invoice.id
        ]
        self.assertEqual(len(invoice_rows), 1)
        self.assertAlmostEqual(invoice_rows[0]['debit'], 4626675.0, places=2)

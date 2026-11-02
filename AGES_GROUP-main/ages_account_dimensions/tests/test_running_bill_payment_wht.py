# -*- coding: utf-8 -*-

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestRunningBillPaymentWht(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.withholding_tax_base_account_id:
            company.withholding_tax_base_account_id = cls.company_data['default_account_assets'].id

        cls.wht_advance = cls.env['account.tax'].create({
            'name': 'WH TAX -7.5% Test',
            'amount': -7.5,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'is_withholding_tax_on_payment': True,
            'company_id': company.id,
        })
        cls.wht_srb = cls.env['account.tax'].create({
            'name': 'WHSRB 20/80 Test',
            'amount': -20.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_scope': 'service',
            'is_withholding_tax_on_payment': True,
            'company_id': company.id,
        })
        cls.wht_other = cls.env['account.tax'].create({
            'name': 'Other WHT Test',
            'amount': -1.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'is_withholding_tax_on_payment': True,
            'company_id': company.id,
        })
        cls.sales_tax = cls.env['account.tax'].create({
            'name': 'SST 15% Test',
            'amount': 15.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_scope': 'service',
            'company_id': company.id,
        })
        cls.sub_company = cls.env['ages.sub.company'].create({
            'name': 'RB Pay Active Co',
            'short_code': 'RBP',
            'company_id': company.id,
            'sales_tax_ids': [(6, 0, [cls.sales_tax.id])],
            'wth_tax_ids': [(6, 0, [cls.wht_advance.id])],
            'wth_on_sales_tax_ids': [(6, 0, [cls.wht_srb.id])],
        })
        project_vals = {
            'name': 'RB Pay Project',
            'partner_id': cls.partner_a.id,
        }
        if 'ages_sub_company_id' in cls.env['project.project']._fields:
            project_vals['ages_sub_company_id'] = cls.sub_company.id
        cls.project = cls.env['project.project'].create(project_vals)
        cls.contract = cls.env['ages.contract'].create({
            'partner_id': cls.partner_a.id,
            'project_id': cls.project.id,
            'sub_company_id': cls.sub_company.id,
            'company_id': company.id,
            'total_work_done_value': 20000,
            'wth_tax_id': cls.wht_advance.id,
            'wth_on_sales_tax_id': cls.wht_srb.id,
        })
        cls.contract.with_context(ages_skip_lock=True).write({'state': 'running'})
        cls.bill = cls.env['ages.running.bill'].create({
            'partner_id': cls.partner_a.id,
            'contract_id': cls.contract.id,
            'project_id': cls.project.id,
            'company_id': company.id,
            'value_of_work_done': 10000.0,
            'wth_tax_id': cls.wht_advance.id,
            'wth_on_sales_tax_id': cls.wht_srb.id,
            'sales_tax_id': cls.sales_tax.id,
            'sales_tax_amount_base': 'work_done_ex_rebate_mr',
        })
        income = cls.company_data['default_account_revenue']
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': '2026-09-20',
            'ages_running_bill_id': cls.bill.id,
            'ages_contract_id': cls.contract.id,
            'ages_sub_company_id': cls.sub_company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Running bill work',
                'quantity': 1,
                'price_unit': 11500.0,
                'account_id': income.id,
            })],
        })
        cls.invoice.action_post()

    def _open_pay_wizard(self):
        receivable = self.invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=self.invoice.ids,
        ).create({
            'line_ids': [(6, 0, receivable.ids)],
            'journal_id': self.company_data['default_journal_bank'].id,
            'ages_sub_company_id': self.sub_company.id,
            'ages_running_bill_id': self.bill.id,
        })
        wizard._compute_amount()
        wizard._compute_withholding_line_ids()
        return wizard

    def _expected_receive_gross(self, bill=None, receive=None, wht_tax=None):
        bill = bill or self.bill
        receive = abs(receive if receive is not None else bill.net_amount)
        tax = wht_tax if wht_tax is not None else self.wht_advance
        rate = abs(tax.amount or 0.0) / 100.0 if tax else 0.0
        currency = bill.currency_id
        receive = currency.round(receive)
        keep = 1.0 - rate
        gross = currency.round(receive / keep) if keep else receive
        wht = currency.round(gross * rate)
        return receive, wht, gross

    def test_running_bill_invoiced_amount_matches_invoice_total(self):
        self.assertAlmostEqual(
            self.bill.invoiced_amount,
            self.invoice.amount_total,
            places=2,
        )

    def test_invoiced_sales_tax_books_full_amount(self):
        """Positive SRB invoice line is 100% sales tax (WTH share is a separate debit)."""
        invoiced = self.bill._ages_invoiced_sales_tax_amount()
        self.assertAlmostEqual(invoiced, abs(self.bill.sales_tax_amount), places=2)
        withheld = self.bill._ages_invoiced_wth_on_sales_tax_amount()
        self.assertAlmostEqual(withheld, abs(self.bill.wth_on_sales_tax_amount), places=2)

    def test_pay_defaults_to_net_plus_wht_without_srb(self):
        wizard = self._open_pay_wizard()
        receive, wht, expected_gross = self._expected_receive_gross()
        self.assertTrue(expected_gross)
        self.assertTrue(wizard.ages_show_actual_amount)
        self.assertAlmostEqual(wizard.ages_actual_amount, receive, places=2)
        self.assertAlmostEqual(wizard.amount, expected_gross, places=2)

        taxes = wizard.withholding_line_ids.mapped('tax_id')
        self.assertIn(self.wht_advance, taxes)
        self.assertNotIn(self.wht_srb, taxes)
        self.assertEqual(len(wizard.withholding_line_ids), 1)

        wht_line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == self.wht_advance)
        self.assertAlmostEqual(wht_line.base_amount, expected_gross, places=2)
        self.assertAlmostEqual(wht_line.amount, wht, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, receive, places=2)

    def test_pay_drops_srb_and_other_tax(self):
        wizard = self._open_pay_wizard()
        wizard._ages_append_withholding_command(
            wizard._ages_prepare_withholding_command(self.wht_other, 1000.0, 10.0)
        )
        wizard._ages_append_withholding_command(
            wizard._ages_prepare_withholding_command(
                self.wht_srb,
                abs(self.bill.sales_tax_amount),
                abs(self.bill.wth_on_sales_tax_amount),
            )
        )
        self.assertIn(self.wht_srb, wizard.withholding_line_ids.mapped('tax_id'))
        wizard.ages_wht_autofill_done = False
        wizard._compute_withholding_line_ids()
        taxes = wizard.withholding_line_ids.mapped('tax_id')
        self.assertIn(self.wht_advance, taxes)
        self.assertNotIn(self.wht_srb, taxes)
        self.assertNotIn(self.wht_other, taxes)
        self.assertEqual(len(wizard.withholding_line_ids), 1)

    def test_pay_debit_change_adds_wht_only(self):
        wizard = self._open_pay_wizard()
        debit = 4625.0
        wizard.amount = debit
        wizard._onchange_amount()
        receive, wht, expected_gross = self._expected_receive_gross(receive=debit)
        self.assertAlmostEqual(wizard.amount, expected_gross, places=2)

        wht_line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == self.wht_advance)
        self.assertTrue(wht_line)
        self.assertNotIn(self.wht_srb, wizard.withholding_line_ids.mapped('tax_id'))
        self.assertAlmostEqual(wht_line.base_amount, expected_gross, places=2)
        self.assertAlmostEqual(wht_line.amount, wht, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, debit, places=1)

        wizard._onchange_amount()
        self.assertAlmostEqual(wizard.amount, expected_gross, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, debit, places=1)

    def test_pay_grosses_bank_by_one_minus_rate(self):
        wizard = self._open_pay_wizard()
        bank = 4948373.0
        wizard.amount = bank
        wizard._onchange_amount()
        expected = wizard.currency_id.round(bank / 0.925)
        self.assertAlmostEqual(wizard.amount, expected, places=2)
        self.assertAlmostEqual(wizard.amount, 5349592.43, places=2)
        line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == self.wht_advance)
        self.assertAlmostEqual(line.base_amount, expected, places=2)
        self.assertAlmostEqual(line.amount, expected * 0.075, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, bank, places=1)

    def test_pay_actual_amount_fills_amount_and_tax(self):
        wizard = self._open_pay_wizard()
        actual = 2869853.25
        wizard.ages_actual_amount = actual
        wizard._onchange_ages_actual_amount()
        expected = wizard.currency_id.round(actual / 0.925)
        self.assertAlmostEqual(wizard.ages_actual_amount, actual, places=2)
        self.assertAlmostEqual(wizard.amount, expected, places=2)
        self.assertAlmostEqual(wizard.amount, 3102544.05, places=2)
        line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == self.wht_advance)
        self.assertAlmostEqual(line.base_amount, expected, places=2)
        self.assertAlmostEqual(line.amount, expected * 0.075, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, actual, places=1)

    def test_pay_snaps_one_paisa_over_residual(self):
        wizard = self._open_pay_wizard()
        residual = wizard._ages_invoice_amount_for_difference()
        self.assertTrue(residual)
        wizard.amount = residual + 0.01
        wizard._onchange_amount()
        self.assertAlmostEqual(wizard.amount, residual, places=2)
        self.assertAlmostEqual(wizard.payment_difference, 0.0, places=2)
        line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == self.wht_advance)
        self.assertAlmostEqual(line.base_amount, residual, places=2)

    def test_pay_typed_net_adds_wht_only(self):
        wizard = self._open_pay_wizard()
        debit = abs(self.bill.net_amount)
        wizard.amount = debit
        wizard._onchange_amount()
        receive, wht, expected_gross = self._expected_receive_gross(receive=debit)
        self.assertAlmostEqual(wizard.amount, expected_gross, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, debit, places=1)
        wht_line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == self.wht_advance)
        self.assertAlmostEqual(wht_line.base_amount, expected_gross, places=2)
        self.assertAlmostEqual(wht_line.amount, wht, places=2)
        self.assertNotIn(self.wht_srb, wizard.withholding_line_ids.mapped('tax_id'))

    def test_pay_journal_empty_and_required(self):
        receivable = self.invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=self.invoice.ids,
        ).create({
            'line_ids': [(6, 0, receivable.ids)],
            'ages_sub_company_id': self.sub_company.id,
            'ages_running_bill_id': self.bill.id,
        })
        self.assertFalse(wizard.journal_id)
        with self.assertRaises(UserError):
            wizard.action_create_payments()

    def test_pay_creates_single_journal_entry(self):
        wizard = self._open_pay_wizard()
        payments = wizard._create_payments()
        self.assertEqual(len(payments), 1)
        moves = self.env['account.move'].search([
            ('origin_payment_id', '=', payments.id),
        ])
        self.assertEqual(
            len(moves),
            1,
            'Create Payment must post one journal entry, not a leftover draft plus a posted copy.',
        )
        self.assertEqual(payments.move_id, moves)
        self.assertEqual(len(payments.withholding_line_ids), 1)
        self.assertNotIn(self.wht_srb, payments.withholding_line_ids.mapped('tax_id'))

    def _create_pay_case(self, wht_tax, sales_wht_tax=None, suffix='X'):
        company = self.env.company
        allowed_sales = [self.sales_tax.id]
        allowed_wht = [self.wht_advance.id, self.wht_other.id]
        allowed_srb = [self.wht_srb.id]
        if wht_tax:
            allowed_wht.append(wht_tax.id)
        if sales_wht_tax:
            allowed_srb.append(sales_wht_tax.id)
        sub = self.env['ages.sub.company'].create({
            'name': 'RB Pay %s' % suffix,
            'short_code': suffix[:5],
            'company_id': company.id,
            'sales_tax_ids': [(6, 0, allowed_sales)],
            'wth_tax_ids': [(6, 0, list(set(allowed_wht)))],
            'wth_on_sales_tax_ids': [(6, 0, list(set(allowed_srb)))],
        })
        project_vals = {
            'name': 'RB Pay Project %s' % suffix,
            'partner_id': self.partner_a.id,
        }
        if 'ages_sub_company_id' in self.env['project.project']._fields:
            project_vals['ages_sub_company_id'] = sub.id
        project = self.env['project.project'].create(project_vals)
        contract_vals = {
            'partner_id': self.partner_a.id,
            'project_id': project.id,
            'sub_company_id': sub.id,
            'company_id': company.id,
            'total_work_done_value': 20000,
            'wth_tax_id': wht_tax.id if wht_tax else False,
            'wth_on_sales_tax_id': sales_wht_tax.id if sales_wht_tax else False,
        }
        contract = self.env['ages.contract'].create(contract_vals)
        contract.with_context(ages_skip_lock=True).write({'state': 'running'})
        bill = self.env['ages.running.bill'].create({
            'partner_id': self.partner_a.id,
            'contract_id': contract.id,
            'project_id': project.id,
            'company_id': company.id,
            'value_of_work_done': 10000.0,
            'wth_tax_id': wht_tax.id if wht_tax else False,
            'wth_on_sales_tax_id': sales_wht_tax.id if sales_wht_tax else False,
            'sales_tax_id': self.sales_tax.id,
            'sales_tax_amount_base': 'work_done_ex_rebate_mr',
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-09-20',
            'ages_running_bill_id': bill.id,
            'ages_contract_id': contract.id,
            'ages_sub_company_id': sub.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Running bill work %s' % suffix,
                'quantity': 1,
                'price_unit': 11500.0,
                'account_id': self.company_data['default_account_revenue'].id,
            })],
        })
        invoice.action_post()
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids,
        ).create({
            'line_ids': [(6, 0, receivable.ids)],
            'journal_id': self.company_data['default_journal_bank'].id,
            'ages_sub_company_id': sub.id,
            'ages_running_bill_id': bill.id,
        })
        wizard._compute_amount()
        wizard._compute_withholding_line_ids()
        return bill, wizard

    def test_pay_follows_contract_wht_only(self):
        wht5 = self.env['account.tax'].create({
            'name': 'WH TAX -5% Test',
            'amount': -5.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'is_withholding_tax_on_payment': True,
            'company_id': self.env.company.id,
        })
        bill, wizard = self._create_pay_case(wht5, None, suffix='W5')
        self.assertTrue(bill.wth_amount)
        self.assertFalse(bill.wth_on_sales_tax_id)
        self.assertEqual(wizard.withholding_line_ids.tax_id, wht5)
        receive, wht, expected = self._expected_receive_gross(
            bill=bill, receive=abs(bill.net_amount), wht_tax=wht5
        )
        self.assertAlmostEqual(wizard.amount, expected, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, receive, places=2)
        self.assertAlmostEqual(wizard.withholding_line_ids.base_amount, expected, places=2)

        debit = 4750.0
        wizard.amount = debit
        wizard._onchange_amount()
        _recv, _wht, expected_debit = self._expected_receive_gross(
            bill=bill, receive=debit, wht_tax=wht5
        )
        self.assertAlmostEqual(wizard.amount, expected_debit, places=2)
        self.assertEqual(wizard.withholding_line_ids.tax_id, wht5)
        self.assertAlmostEqual(wizard.withholding_line_ids.base_amount, expected_debit, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, debit, places=1)

    def test_pay_follows_contract_custom_rates(self):
        wht10 = self.env['account.tax'].create({
            'name': 'WH TAX -10% Test',
            'amount': -10.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'is_withholding_tax_on_payment': True,
            'company_id': self.env.company.id,
        })
        sales15 = self.env['account.tax'].create({
            'name': 'WTH on ST -15% Test',
            'amount': -15.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_scope': 'service',
            'is_withholding_tax_on_payment': True,
            'company_id': self.env.company.id,
        })
        bill, wizard = self._create_pay_case(wht10, sales15, suffix='C15')
        taxes = wizard.withholding_line_ids.mapped('tax_id')
        self.assertIn(wht10, taxes)
        self.assertNotIn(sales15, taxes)
        self.assertNotIn(self.wht_advance, taxes)
        self.assertNotIn(self.wht_srb, taxes)
        receive, wht, expected = self._expected_receive_gross(
            bill=bill, receive=abs(bill.net_amount), wht_tax=wht10
        )
        self.assertAlmostEqual(wizard.amount, expected, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, receive, places=2)
        wht_line = wizard.withholding_line_ids.filtered(lambda rec: rec.tax_id == wht10)
        self.assertAlmostEqual(wht_line.base_amount, expected, places=2)
        self.assertEqual(len(wizard.withholding_line_ids), 1)

        debit = abs(bill.net_amount)
        wizard.amount = debit
        wizard._onchange_amount()
        self.assertAlmostEqual(wizard.amount, expected, places=2)
        self.assertAlmostEqual(wizard.withholding_net_amount, debit, places=1)

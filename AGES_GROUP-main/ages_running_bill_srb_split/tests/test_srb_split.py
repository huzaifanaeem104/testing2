# -*- coding: utf-8 -*-

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestRunningBillSrbSplit(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.withholding_tax_base_account_id:
            company.withholding_tax_base_account_id = cls.company_data['default_account_assets'].id
        cls.wht_advance = cls.env['account.tax'].create({
            'name': 'WH TAX -7.5% SRB Split',
            'amount': -7.5,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'is_withholding_tax_on_payment': True,
            'company_id': company.id,
        })
        cls.wht_srb = cls.env['account.tax'].create({
            'name': 'WHSRB 20/80 Split',
            'amount': -20.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_scope': 'service',
            'is_withholding_tax_on_payment': True,
            'company_id': company.id,
        })
        cls.sales_tax = cls.env['account.tax'].create({
            'name': 'SST 15% Split',
            'amount': 15.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_scope': 'service',
            'company_id': company.id,
        })
        cls.srb_account = cls.env['account.account'].create({
            'name': 'SRB Payable Split',
            'code': '201008S',
            'account_type': 'liability_current',
            'reconcile': False,
        })
        tax_lines = cls.sales_tax.invoice_repartition_line_ids.filtered(
            lambda line: line.repartition_type == 'tax'
        )
        tax_lines.account_id = cls.srb_account.id
        company.ages_work_done_account_id = cls.company_data['default_account_revenue']
        company.ages_mobilization_account_id = cls.company_data['default_account_revenue']
        company.ages_retention_account_id = cls.company_data['default_account_assets']
        cls.sub_company = cls.env['ages.sub.company'].create({
            'name': 'SRB Split Co',
            'short_code': 'SRB',
            'company_id': company.id,
            'sales_tax_ids': [(6, 0, [cls.sales_tax.id])],
            'wth_tax_ids': [(6, 0, [cls.wht_advance.id])],
            'wth_on_sales_tax_ids': [(6, 0, [cls.wht_srb.id])],
        })
        project_vals = {
            'name': 'SRB Split Project',
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
            'mobilization_percent': 10.0,
            'retention_percent': 5.0,
        })

    def test_new_invoice_srb_credit_100_debit_20(self):
        invoice = self.bill._create_and_post_invoice()
        full_st = abs(self.bill.sales_tax_amount)
        withheld = abs(self.bill.wth_on_sales_tax_amount)
        # Retention account is receivable → payment-term split (not a product line).
        expected_total = (
            abs(self.bill.ex_rebate_mr_value)
            + full_st
            - withheld
            - abs(self.bill.mobilization_amount)
        )
        self.assertAlmostEqual(invoice.amount_total, expected_total, places=2)
        self.assertAlmostEqual(
            invoice.amount_total,
            self.bill._ages_expected_invoice_total(),
            places=2,
        )

        srb_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.account_id == self.srb_account and line.display_type == 'product'
        )
        self.assertEqual(len(srb_lines), 2)
        credit_line = srb_lines.filtered(lambda line: line.price_unit > 0)
        debit_line = srb_lines.filtered(lambda line: line.price_unit < 0)
        self.assertEqual(len(credit_line), 1)
        self.assertEqual(len(debit_line), 1)
        self.assertAlmostEqual(credit_line.price_unit, full_st, places=2)
        self.assertAlmostEqual(debit_line.price_unit, -withheld, places=2)

        # Posted move: SRB credit 100%, debit 20%, net credit 80%
        srb_move_lines = invoice.line_ids.filtered(lambda line: line.account_id == self.srb_account)
        self.assertAlmostEqual(sum(srb_move_lines.mapped('credit')), full_st, places=2)
        self.assertAlmostEqual(sum(srb_move_lines.mapped('debit')), withheld, places=2)
        self.assertAlmostEqual(
            sum(srb_move_lines.mapped('credit')) - sum(srb_move_lines.mapped('debit')),
            full_st - withheld,
            places=2,
        )

        self.assertTrue(invoice.invoice_line_ids.filtered(
            lambda line: 'Mobilization' in (line.name or '')
        ))
        # Retention receivable → due-date payment term, not invoice product line
        ret_terms = invoice.line_ids.filtered(
            lambda line: line.display_type == 'payment_term'
            and 'Retained' in (line.name or '')
        )
        self.assertTrue(ret_terms)
        self.assertTrue(all(ret_terms.mapped('date_maturity')))
        self.assertFalse(invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == 'line_note'
        ))
    def test_existing_invoice_credit_clears_withheld_share(self):
        """AGES-SRB-WHT credit notes are disabled; clear is a no-op."""
        income = self.company_data['default_account_revenue']
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-09-20',
            'ages_running_bill_id': self.bill.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Full receivable',
                'quantity': 1,
                'price_unit': abs(self.bill.total_receivable) or 11500.0,
                'account_id': income.id,
            })],
        })
        invoice.action_post()
        residual_before = invoice.amount_residual
        refunds = invoice._ages_clear_withheld_sales_tax()
        self.assertFalse(refunds)
        self.assertAlmostEqual(invoice.amount_residual, residual_before, places=2)

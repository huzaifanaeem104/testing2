# -*- coding: utf-8 -*-

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestAgesExpense(AccountTestInvoicingCommon):

    def test_expense_gets_voucher_on_save(self):
        expense = self.env['ages.expense'].create({
            'description': 'Petty cash voucher test',
            'journal_id': self.company_data['default_journal_cash'].id,
            'date': fields.Date.today(),
        })
        self.assertTrue(expense.name)
        self.assertNotIn(expense.name, ('New', '/', False))
        self.assertTrue(expense.name.startswith('EXP/'))

    def test_bank_journal_skips_payment_analytic(self):
        expense = self.env['ages.expense'].new({
            'description': 'Bank payment expense',
            'journal_id': self.company_data['default_journal_bank'].id,
            'apply_100_payment_analytic': True,
        })
        expense._onchange_journal_id()
        self.assertFalse(expense.apply_100_payment_analytic)
        self.assertFalse(expense.payment_analytic_account_id)
        self.assertFalse(expense._ages_payment_analytic_distribution())

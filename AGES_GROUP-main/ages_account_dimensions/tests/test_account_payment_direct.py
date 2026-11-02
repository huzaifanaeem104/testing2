# -*- coding: utf-8 -*-

import re

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestAgesDirectPayment(AccountTestInvoicingCommon):

    def test_direct_payment_project_does_not_fill_contract(self):
        sub_company = self.env['ages.sub.company'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        ) or self.env['ages.sub.company'].create({
            'name': 'Test Active Company',
            'short_code': 'TAC',
            'company_id': self.env.company.id,
        })
        project = self.env['project.project'].create({
            'name': 'Multi Contract Project',
            'ages_sub_company_id': sub_company.id,
        })
        contract = self.env['ages.contract'].create({
            'partner_id': self.partner_a.id,
            'project_id': project.id,
            'sub_company_id': sub_company.id,
            'company_id': self.env.company.id,
        })
        project.ages_contract_id = contract.id

        payment = self.env['account.payment'].new({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_a.id,
            'amount': 50.0,
        })
        payment.ages_project_id = project
        payment._onchange_ages_project_id()
        self.assertFalse(payment.ages_contract_id)
        self.assertEqual(payment.ages_sub_company_id, sub_company)

    def test_bill_project_fills_active_company(self):
        sub_company = self.env['ages.sub.company'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        ) or self.env['ages.sub.company'].create({
            'name': 'Test Active Company',
            'short_code': 'TAC',
            'company_id': self.env.company.id,
        })
        project = self.env['project.project'].create({
            'name': 'Bill Project',
            'ages_sub_company_id': sub_company.id,
        })
        move = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
        })
        move.ages_project_id = project
        move._onchange_ages_project_id()
        self.assertEqual(move.ages_sub_company_id, sub_company)

    def _ages_payment_analytic_account(self, name='AGES Payment Analytic'):
        plan = self.env['account.analytic.plan'].search([], limit=1) or self.env['account.analytic.plan'].create({
            'name': 'AGES Test Plan',
        })
        return self.env['account.analytic.account'].create({
            'name': name,
            'plan_id': plan.id,
            'company_id': self.env.company.id,
        })

    def test_payment_gets_journal_sequence_on_save(self):
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_a.id,
            'amount': 25.0,
            'journal_id': self.company_data['default_journal_bank'].id,
        })
        self.assertEqual(payment.state, 'draft')
        self.assertTrue(payment.move_id)
        self.assertEqual(payment.move_id.state, 'draft')
        self.assertTrue(payment.name)
        self.assertNotEqual(payment.name, '/')
        self.assertFalse(re.match(r'^PAY\d+$', payment.name.upper()))
        self.assertEqual(payment.name, payment.move_id.name)
        reserved_name = payment.name
        payment.action_post()
        self.assertEqual(payment.name, reserved_name)
        self.assertEqual(payment.move_id.name, reserved_name)
        self.assertEqual(payment.move_id.state, 'posted')

    def test_vendors_transfer_splits_payable_debits(self):
        payment_aa = self._ages_payment_analytic_account()
        line_aa = self._ages_payment_analytic_account('Vendor Line Analytic')
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'is_vendors_transfer': True,
            'ages_apply_100_payment_analytic': True,
            'ages_payment_analytic_account_id': payment_aa.id,
            'amount': 0.0,
            'payment_detail_line_ids': [
                (0, 0, {
                    'partner_id': self.partner_a.id,
                    'amount': 40.0,
                    'description': 'Bricks',
                    'analytic_distribution': {str(line_aa.id): 100.0},
                }),
                (0, 0, {
                    'partner_id': self.partner_b.id,
                    'amount': 60.0,
                    'description': 'Roller',
                    'analytic_distribution': {str(line_aa.id): 100.0},
                }),
            ],
        })
        self.assertEqual(payment.amount, 100.0)
        self.assertFalse(payment.partner_id)
        self.assertTrue(payment.move_id)
        self.assertEqual(payment.move_id.state, 'draft')
        self.assertTrue(payment.name)
        self.assertFalse(re.match(r'^PAY\d+$', (payment.name or '').upper()))
        self.assertEqual(payment.name, payment.move_id.name)
        reserved_name = payment.name
        payment.action_post()
        self.assertEqual(payment.name, reserved_name)
        self.assertEqual(payment.move_id.name, reserved_name)
        self.assertTrue(payment.move_id)
        payable_lines = payment.move_id.line_ids.filtered(lambda line: line.debit)
        credit_lines = payment.move_id.line_ids.filtered(lambda line: line.credit)
        self.assertEqual(len(payable_lines), 2)
        self.assertEqual(len(credit_lines), 1)
        self.assertAlmostEqual(sum(payable_lines.mapped('debit')), 100.0)
        self.assertAlmostEqual(credit_lines.debit, 0.0)
        self.assertAlmostEqual(credit_lines.credit, 100.0)
        self.assertEqual(
            set(payable_lines.mapped('partner_id')),
            {self.partner_a, self.partner_b},
        )
        self.assertEqual(credit_lines.analytic_distribution, {str(payment_aa.id): 100.0})
        for line in payable_lines:
            self.assertEqual(line.analytic_distribution, {str(line_aa.id): 100.0})

    def test_vendors_transfer_journal_credit_without_analytic(self):
        line_aa = self._ages_payment_analytic_account('Vendor Line Analytic')
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'is_vendors_transfer': True,
            'ages_apply_100_payment_analytic': False,
            'amount': 0.0,
            'payment_detail_line_ids': [
                (0, 0, {
                    'partner_id': self.partner_a.id,
                    'amount': 40.0,
                    'description': 'Bricks',
                    'analytic_distribution': {str(line_aa.id): 100.0},
                }),
                (0, 0, {
                    'partner_id': self.partner_b.id,
                    'amount': 60.0,
                    'description': 'Roller',
                    'analytic_distribution': {str(line_aa.id): 100.0},
                }),
            ],
        })
        payment.action_post()
        credit_lines = payment.move_id.line_ids.filtered(lambda line: line.credit)
        self.assertEqual(len(credit_lines), 1)
        self.assertEqual(credit_lines.account_id, payment._ages_liquidity_account())
        self.assertFalse(credit_lines.analytic_distribution)
        payable_lines = payment.move_id.line_ids.filtered(lambda line: line.debit)
        for line in payable_lines:
            self.assertEqual(line.analytic_distribution, {str(line_aa.id): 100.0})

    def test_internal_transfer_journal_credit_analytic_optional(self):
        dest_journal = self.company_data['default_journal_cash']
        source_journal = self.company_data['default_journal_bank']
        payment_aa = self._ages_payment_analytic_account()
        without_analytic = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'is_internal_transfer': True,
            'journal_id': source_journal.id,
            'ages_apply_100_payment_analytic': False,
            'amount': 0.0,
            'payment_detail_line_ids': [
                (0, 0, {
                    'destination_journal_id': dest_journal.id,
                    'amount': 75.0,
                    'description': 'To cash',
                }),
            ],
        })
        without_analytic.action_post()
        source_line = without_analytic.move_id.line_ids.filtered(
            lambda line: line.account_id == source_journal.default_account_id
        )
        dest_line = without_analytic.move_id.line_ids.filtered(
            lambda line: line.account_id == dest_journal.default_account_id
        )
        self.assertAlmostEqual(source_line.credit, 75.0)
        self.assertFalse(source_line.analytic_distribution)
        self.assertAlmostEqual(dest_line.debit, 75.0)

        with_analytic = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'is_internal_transfer': True,
            'journal_id': source_journal.id,
            'ages_apply_100_payment_analytic': True,
            'ages_payment_analytic_account_id': payment_aa.id,
            'amount': 0.0,
            'payment_detail_line_ids': [
                (0, 0, {
                    'destination_journal_id': dest_journal.id,
                    'amount': 80.0,
                    'description': 'To cash with analytic',
                }),
            ],
        })
        with_analytic.action_post()
        source_line = with_analytic.move_id.line_ids.filtered(
            lambda line: line.account_id == source_journal.default_account_id
        )
        self.assertAlmostEqual(source_line.credit, 80.0)
        self.assertEqual(source_line.analytic_distribution, {str(payment_aa.id): 100.0})

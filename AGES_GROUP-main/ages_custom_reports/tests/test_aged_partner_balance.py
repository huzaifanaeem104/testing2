# -*- coding: utf-8 -*-

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

from ..report.aged_partner_balance_engine import AgedPartnerBalanceEngine


@tagged('post_install', '-at_install')
class TestAgedPartnerBalance(AccountTestInvoicingCommon):

    @classmethod
    def setup_independent_user(cls):
        # AGES payroll extends company creation with manager-only setup records.
        # Keep the standard test transaction on the superuser for that hook.
        return None

    def setUp(self):
        super().setUp()
        self.receivable = self.company_data['default_account_receivable']
        self.payable = self.company_data['default_account_payable']
        self.counterpart = self.company_data['default_account_revenue']
        self.misc_journal = self.company_data['default_journal_misc']

    def _create_partner(self, name):
        return self.env['res.partner'].create({'name': name})

    def _create_open_line(
        self,
        amount,
        *,
        account=None,
        counterpart=None,
        journal=None,
        partner=None,
        move_date='2099-01-01',
        invoice_date=None,
        due_date=None,
        currency=None,
        amount_currency=None,
        reference='AGES aging test',
    ):
        account = account or self.receivable
        counterpart = counterpart or self.counterpart
        journal = journal or self.misc_journal
        invoice_date = invoice_date or move_date
        line_vals = {
            'name': reference,
            'account_id': account.id,
            'partner_id': partner.id if partner else False,
            'debit': amount if amount > 0 else 0.0,
            'credit': -amount if amount < 0 else 0.0,
            'date_maturity': due_date or move_date,
        }
        counterpart_vals = {
            'name': reference,
            'account_id': counterpart.id,
            'debit': -amount if amount < 0 else 0.0,
            'credit': amount if amount > 0 else 0.0,
        }
        if currency:
            line_vals.update({
                'currency_id': currency.id,
                'amount_currency': amount_currency,
            })
            counterpart_vals.update({
                'currency_id': currency.id,
                'amount_currency': -amount_currency,
            })
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': move_date,
            'invoice_date': invoice_date,
            'ref': reference,
            'line_ids': [
                Command.create(line_vals),
                Command.create(counterpart_vals),
            ],
        })
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == account)

    def _engine(self, partner_ids=None, engine_env=None, **overrides):
        options = {
            'report_type': 'receivable',
            'date_to': '2099-05-01',
            'aging_based_on': 'maturity',
            'aging_interval': 30,
            'partner_ids': partner_ids or [],
            'filter_trade': True,
            'filter_non_trade': False,
            'show_currency': False,
            'show_account': False,
            'hide_zero_lines': False,
            'all_entries': False,
            'unfold_all': False,
            'sort_by': 'name',
            'sort_direction': 'asc',
        }
        options.update(overrides)
        return AgedPartnerBalanceEngine(engine_env or self.env, options)

    @staticmethod
    def _partner_lines(report_data):
        return [
            line for line in report_data['lines']
            if line['line_type'] == 'partner'
        ]

    def test_bucket_boundaries_for_30_and_60_days(self):
        partner = self._create_partner('AGES Bucket Boundary Partner')
        due_dates = [
            '2099-05-01',  # At date.
            '2099-04-30',  # 1 day.
            '2099-04-01',  # 30 days.
            '2099-03-31',  # 31 days.
            '2099-03-02',  # 60 days.
            '2099-03-01',  # 61 days.
            '2099-01-01',  # 120 days.
            '2098-12-31',  # 121 days.
        ]
        for index, due_date in enumerate(due_dates):
            self._create_open_line(
                10.0,
                partner=partner,
                move_date='2098-12-01',
                due_date=due_date,
                reference=f'Boundary {index}',
            )

        line = self._partner_lines(
            self._engine([partner.id]).get_report_data()
        )[0]
        self.assertEqual(
            [line[f'period{index}'] for index in range(6)],
            [10.0, 20.0, 20.0, 10.0, 10.0, 10.0],
        )

        engine_60 = self._engine([partner.id], aging_interval=60)
        line_60 = self._partner_lines(engine_60.get_report_data())[0]
        self.assertEqual(
            [line_60[f'period{index}'] for index in range(6)],
            [10.0, 40.0, 20.0, 10.0, 0.0, 0.0],
        )
        self.assertEqual(engine_60._period_labels()['period2'], '61-120')

    def test_due_date_and_invoice_date_basis(self):
        partner = self._create_partner('AGES Aging Basis Partner')
        self._create_open_line(
            50.0,
            partner=partner,
            move_date='2099-03-01',
            invoice_date='2099-03-01',
            due_date='2099-04-20',
        )

        due_line = self._partner_lines(
            self._engine([partner.id], aging_based_on='maturity').get_report_data()
        )[0]
        invoice_line = self._partner_lines(
            self._engine([partner.id], aging_based_on='invoice').get_report_data()
        )[0]
        self.assertEqual(due_line['period1'], 50.0)
        self.assertEqual(invoice_line['period3'], 50.0)

    def test_partial_reconcile_is_applied_only_from_its_max_date(self):
        partner = self._create_partner('AGES Historical Residual Partner')
        invoice_line = self._create_open_line(
            100.0,
            partner=partner,
            move_date='2099-01-01',
            due_date='2099-01-01',
            reference='Historical invoice',
        )
        payment_line = self._create_open_line(
            -40.0,
            partner=partner,
            move_date='2099-02-15',
            due_date='2099-02-15',
            reference='Later payment',
        )
        (invoice_line + payment_line).reconcile()

        before_payment = self._partner_lines(
            self._engine(
                [partner.id],
                date_to='2099-01-31',
            ).get_report_data()
        )[0]
        after_payment = self._partner_lines(
            self._engine(
                [partner.id],
                date_to='2099-02-28',
            ).get_report_data()
        )[0]
        self.assertEqual(before_payment['total'], 100.0)
        self.assertEqual(after_payment['total'], 60.0)

    def test_receivable_payable_signs_and_refunds(self):
        partner = self._create_partner('AGES Sign Partner')
        self._create_open_line(100.0, partner=partner)
        self._create_open_line(
            -25.0,
            partner=partner,
            reference='Customer refund',
        )
        self._create_open_line(
            -100.0,
            account=self.payable,
            partner=partner,
            reference='Vendor bill',
        )
        self._create_open_line(
            25.0,
            account=self.payable,
            partner=partner,
            reference='Vendor refund',
        )

        receivable = self._partner_lines(
            self._engine([partner.id], report_type='receivable').get_report_data()
        )[0]
        payable = self._partner_lines(
            self._engine([partner.id], report_type='payable').get_report_data()
        )[0]
        self.assertEqual(receivable['total'], 75.0)
        self.assertEqual(payable['total'], 75.0)

    def test_unknown_partner_foreign_currency_and_zero_net_partner(self):
        non_trade = self.receivable.copy({
            'name': 'AGES Test Non-Trade Receivable',
            'code': 'ZNTREC99',
            'non_trade': True,
        })
        unknown_line = self._create_open_line(
            17.0,
            account=non_trade,
            partner=None,
            currency=self.env.ref('base.USD'),
            amount_currency=23.0,
            reference='Unknown foreign item',
        )
        unknown_report = self._engine(
            filter_trade=False,
            filter_non_trade=True,
            unfold_all=True,
            show_currency=True,
        ).get_report_data()
        unknown_partners = [
            line for line in self._partner_lines(unknown_report)
            if not line['partner_id']
        ]
        self.assertTrue(unknown_partners)
        unknown_children = unknown_partners[0]['children']
        detail = next(
            line for line in unknown_children
            if line['move_line_id'] == unknown_line.id
        )
        self.assertEqual(detail['amount_currency'], 23.0)
        self.assertEqual(detail['currency_name'], 'USD')
        self.assertFalse(detail['total'])

        zero_partner = self._create_partner('AGES Zero Net Partner')
        self._create_open_line(50.0, partner=zero_partner, reference='Zero debit')
        self._create_open_line(-50.0, partner=zero_partner, reference='Zero credit')
        visible = self._partner_lines(
            self._engine([zero_partner.id], unfold_all=True).get_report_data()
        )
        hidden = self._partner_lines(
            self._engine(
                [zero_partner.id],
                hide_zero_lines=True,
            ).get_report_data()
        )
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]['total'], 0.0)
        self.assertEqual(len(visible[0]['children']), 2)
        self.assertFalse(hidden)

    def test_draft_entries_are_excluded_until_enabled(self):
        partner = self._create_partner('AGES Draft Partner')
        self._create_open_line(
            100.0,
            partner=partner,
            due_date='2099-05-01',
            reference='Posted aging line',
        )
        draft_move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.misc_journal.id,
            'date': '2099-04-01',
            'invoice_date': '2099-04-01',
            'ref': 'Draft aging line',
            'line_ids': [
                Command.create({
                    'name': 'Draft aging line',
                    'account_id': self.receivable.id,
                    'partner_id': partner.id,
                    'debit': 40.0,
                    'credit': 0.0,
                    'date_maturity': '2099-04-01',
                }),
                Command.create({
                    'name': 'Draft aging line',
                    'account_id': self.counterpart.id,
                    'debit': 0.0,
                    'credit': 40.0,
                }),
            ],
        })
        self.assertEqual(draft_move.state, 'draft')
        posted_only = self._partner_lines(
            self._engine([partner.id]).get_report_data()
        )
        with_draft = self._partner_lines(
            self._engine([partner.id], all_entries=True).get_report_data()
        )
        self.assertEqual(posted_only[0]['total'], 100.0)
        self.assertEqual(with_draft[0]['total'], 140.0)

    def test_partner_trade_filters_sorting_and_exact_bucket_ids(self):
        partner_a = self._create_partner('AGES Sort A')
        partner_b = self._create_partner('AGES Sort B')
        line_a = self._create_open_line(
            20.0,
            partner=partner_a,
            due_date='2099-04-20',
        )
        self._create_open_line(
            50.0,
            partner=partner_b,
            due_date='2099-03-20',
        )
        sorted_lines = self._partner_lines(
            self._engine(
                [partner_a.id, partner_b.id],
                sort_by='total',
                sort_direction='desc',
            ).get_report_data()
        )
        self.assertEqual(
            [line['partner_id'] for line in sorted_lines],
            [partner_b.id, partner_a.id],
        )

        engine = self._engine([partner_a.id])
        self.assertEqual(
            engine.get_bucket_move_line_ids(partner_a.id, 'period1'),
            line_a.ids,
        )
        self.assertFalse(
            engine.get_bucket_move_line_ids(partner_a.id, 'period2')
        )

        non_trade = self.receivable.copy({
            'name': 'AGES Filter Non-Trade Receivable',
            'code': 'ZNTREC98',
            'non_trade': True,
        })
        self._create_open_line(
            33.0,
            account=non_trade,
            partner=partner_a,
        )
        trade_total = self._partner_lines(
            self._engine([partner_a.id]).get_report_data()
        )[0]['total']
        non_trade_total = self._partner_lines(
            self._engine(
                [partner_a.id],
                filter_trade=False,
                filter_non_trade=True,
            ).get_report_data()
        )[0]['total']
        self.assertEqual(trade_total, 20.0)
        self.assertEqual(non_trade_total, 33.0)

    def test_current_multi_company_selection_is_aggregated(self):
        partner = self._create_partner('AGES Multi Company Partner')
        self._create_open_line(10.0, partner=partner)
        second_company_data = self.setup_other_company(
            name='AGES Aging Second Company'
        )
        self._create_open_line(
            20.0,
            account=second_company_data['default_account_receivable'],
            counterpart=second_company_data['default_account_revenue'],
            journal=second_company_data['default_journal_misc'],
            partner=partner,
            reference='Second company receivable',
        )

        single_company_env = self.env(
            context={
                **self.env.context,
                'allowed_company_ids': [self.env.company.id],
            }
        )
        single_company = self._partner_lines(
            self._engine(
                [partner.id],
                engine_env=single_company_env,
            ).get_report_data()
        )[0]
        multi_company_env = self.env(
            context={
                **self.env.context,
                'allowed_company_ids': [
                    self.env.company.id,
                    second_company_data['company'].id,
                ],
            }
        )
        multi_company = self._partner_lines(
            self._engine(
                [partner.id],
                engine_env=multi_company_env,
            ).get_report_data()
        )[0]
        self.assertEqual(single_company['total'], 10.0)
        self.assertEqual(multi_company['total'], 30.0)

    def test_pdf_template_and_xlsx_generation(self):
        partner = self._create_partner('AGES Export Partner')
        self._create_open_line(125.0, partner=partner)
        wizard = self.env['aged.partner.balance.wizard'].create({
            'report_type': 'receivable',
            'date_to': '2099-05-01',
            'partner_ids': [Command.set(partner.ids)],
            'unfold_all': True,
            'show_account': True,
        })
        data = wizard._get_report_data()

        pdf_action = self.env.ref(
            'ages_custom_reports.action_report_aged_receivable_pdf'
        )
        html, output_type = pdf_action._render_qweb_html(
            pdf_action.report_name,
            wizard.ids,
            data=data,
        )
        self.assertEqual(output_type, 'html')
        self.assertIn(b'Aged Receivable', html)
        self.assertIn(b'AGES Export Partner', html)

        xlsx_model = self.env[
            'report.ages_custom_reports.aged_partner_balance_xlsx'
        ].with_context(
            active_model=wizard._name,
            active_ids=wizard.ids,
        )
        content, output_type = xlsx_model.create_xlsx_report(wizard.ids, data)
        self.assertEqual(output_type, 'xlsx')
        self.assertTrue(content.startswith(b'PK'))

    def test_journal_entry_action_highlights_clicked_line(self):
        partner = self._create_partner('AGES Highlight Partner')
        line = self._create_open_line(50.0, partner=partner)
        wizard = self.env['aged.partner.balance.wizard'].create({
            'report_type': 'receivable',
            'date_to': '2099-05-01',
        })
        action = wizard.action_open_journal_entry(line.move_id.id, line.id)
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['res_id'], line.move_id.id)
        self.assertEqual(action['context']['ages_highlight_move_line_id'], line.id)

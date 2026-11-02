# -*- coding: utf-8 -*-

from odoo.tests.common import tagged

from odoo.addons.ages_custom_reports.report.partner_ledger_engine import PartnerLedgerEngine

from .common import OpalVendorBalanceCase


@tagged('post_install', '-at_install')
class TestOpalPartnerLedgerProjectFilter(OpalVendorBalanceCase):

    def setUp(self):
        super().setUp()
        self._import_sample()
        self.partner = self.env['res.partner'].create({
            'name': 'ABDUL REHMAN CRUSH SUPPLIER | SINDHRI',
            'supplier_rank': 1,
        })
        self.env['opal.vendor.map'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], limit=1).write({'partner_id': self.partner.id})
        self.currency = self.env.company.currency_id
        self.hook = self.env['opal.partner.ledger.hook']

    def _analytic(self, name):
        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            plan = self.env['account.analytic.plan'].create({'name': 'OPAL Test Plan'})
        return self.env['account.analytic.account'].create({
            'name': name,
            'plan_id': plan.id,
        })

    def test_no_project_shows_overall_and_all_projects(self):
        rows = self.hook.get_partner_children(
            self.partner,
            {'show_opal_balance': True},
            self.currency,
        )
        names = [row['name'] for row in rows]
        self.assertEqual(names[0], 'OPAL Overall')
        self.assertTrue(any('SINDHRI' in name for name in names))
        self.assertTrue(any('DEHARKI' in name for name in names))
        self.assertGreaterEqual(len(rows), 3)

    def test_deharki_project_shows_only_that_opal_on_credit(self):
        analytic = self._analytic('DEHARKI SUGAR MILLS')
        rows = self.hook.get_partner_children(
            self.partner,
            {
                'show_opal_balance': True,
                'analytic_account_id': analytic.id,
            },
            self.currency,
        )
        self.assertEqual(len(rows), 1)
        self.assertIn('DEHARKI', rows[0]['name'])
        self.assertNotIn('Overall', rows[0]['name'])
        self.assertAlmostEqual(rows[0]['credit'], 217897.0, places=2)
        self.assertAlmostEqual(rows[0]['debit'], 0.0, places=2)
        self.assertAlmostEqual(rows[0]['balance'], 217897.0, places=2)

    def test_sindhari_sugar_mills_matches_sindhri_opal(self):
        """Odoo analytic 'SINDHARI SUGAR MILLS' must resolve OPAL project SINDHRI."""
        analytic = self._analytic('SINDHARI SUGAR MILLS')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'show_opal_balance': True,
            'unfold_all': True,
        })
        data = engine.get_report_data()
        partner_line = next(
            line for line in data['lines']
            if line.get('partner_id') == self.partner.id
        )
        opal = [child for child in partner_line['children'] if child.get('line_type') == 'opal']
        self.assertEqual(len(opal), 1, 'expected only SINDHRI OPAL row')
        self.assertIn('SINDHRI', opal[0]['name'])
        self.assertNotIn('DEHARKI', opal[0]['name'])
        self.assertAlmostEqual(opal[0]['credit'], 10970428.0, places=2)
        self.assertAlmostEqual(partner_line['credit'], 10970428.0, places=2)
        self.assertAlmostEqual(partner_line['balance'], -10970428.0, places=2)
        total = data['lines'][-1]
        self.assertEqual(total['line_type'], 'total')
        self.assertAlmostEqual(total['balance'], -10970428.0, places=2)

    def test_folded_sindhari_still_shows_opal_and_nets_total(self):
        """No Odoo lines on SINDHARI: still show OPAL 10,970,428 on the partner total."""
        analytic = self._analytic('SINDHARI SUGAR MILLS')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'all',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'analytic_account_name': 'SINDHARI SUGAR MILLS',
            'show_opal_balance': True,
            'unfold_all': False,
        })
        data = engine.get_report_data()
        partner_line = next(
            line for line in data['lines']
            if line.get('partner_id') == self.partner.id
        )
        opal = [child for child in partner_line['children'] if child.get('line_type') == 'opal']
        self.assertEqual(len(opal), 1)
        self.assertIn('SINDHRI', opal[0]['name'])
        self.assertAlmostEqual(opal[0]['credit'], 10970428.0, places=2)
        self.assertAlmostEqual(partner_line['credit'], 10970428.0, places=2)
        self.assertAlmostEqual(partner_line['balance'], -10970428.0, places=2)
        self.assertAlmostEqual(data['lines'][-1]['balance'], -10970428.0, places=2)

    def test_partner_detail_merges_opal_with_odoo_lines(self):
        analytic = self._analytic('DEHARKI SUGAR MILLS')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'show_opal_balance': True,
        })
        # Simulate detail payload that already has an Odoo child (no OPAL yet).
        fake_children = [{
            'id': 'move-fake',
            'name': 'PJSBNK2/2026/00004',
            'line_type': 'move_line',
            'debit': 3000000.0,
            'credit': 0.0,
            'balance': 3000000.0,
            'children': [],
        }]
        # Patch only the original builder path via engine; call patched detail merge.
        from odoo.addons.ages_opal_vendor_balance.report import partner_ledger_opal_patch as patch_mod
        original = patch_mod._original_get_partner_detail

        def _fake_detail(self_engine, partner_id):
            return {'children': list(fake_children)}

        patch_mod._original_get_partner_detail = _fake_detail
        try:
            result = engine.get_partner_detail(self.partner.id)
        finally:
            patch_mod._original_get_partner_detail = original
        types = [child.get('line_type') for child in result['children']]
        self.assertIn('opal', types)
        self.assertIn('move_line', types)
        opal = next(child for child in result['children'] if child.get('line_type') == 'opal')
        self.assertIn('DEHARKI', opal['name'])
        self.assertAlmostEqual(opal['credit'], 217897.0, places=2)
        move = next(child for child in result['children'] if child.get('line_type') == 'move_line')
        self.assertEqual(move['id'], 'move-fake')
        self.assertAlmostEqual(move['debit'], 3000000.0, places=2)

    def test_partner_detail_sindhari_without_odoo_still_returns_opal(self):
        analytic = self._analytic('SINDHARI SUGAR MILLS')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'analytic_account_name': 'SINDHARI SUGAR MILLS',
            'show_opal_balance': True,
        })
        result = engine.get_partner_detail(self.partner.id)
        types = [child.get('line_type') for child in result['children']]
        self.assertIn('opal', types)
        opal = next(child for child in result['children'] if child.get('line_type') == 'opal')
        self.assertIn('SINDHRI', opal['name'])
        self.assertAlmostEqual(opal['credit'], 10970428.0, places=2)

    def test_sindhri_project_shows_opal_even_without_odoo_lines(self):
        analytic = self._analytic('SINDHRI')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'show_opal_balance': True,
            'unfold_all': True,
        })
        data = engine.get_report_data()
        partner_line = next(
            line for line in data['lines']
            if line.get('partner_id') == self.partner.id
        )
        opal = [child for child in partner_line['children'] if child.get('line_type') == 'opal']
        self.assertEqual(len(opal), 1)
        self.assertIn('SINDHRI', opal[0]['name'])
        self.assertAlmostEqual(opal[0]['credit'], 10970428.0, places=2)
        self.assertAlmostEqual(partner_line['credit'], 10970428.0, places=2)
        self.assertAlmostEqual(
            partner_line['balance'],
            partner_line['debit'] - partner_line['credit'],
            places=2,
        )

    def test_project_netting_keeps_odoo_move_lines(self):
        analytic = self._analytic('DEHARKI SUGAR MILLS')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'show_opal_balance': True,
        })
        move_child = {
            'id': 'move_pjsbnk2',
            'name': 'PJSBNK2/2026/00004',
            'line_type': 'move_line',
            'debit': 3000000.0,
            'credit': 0.0,
            'balance': 3000000.0,
            'children': [],
        }
        fake = {
            'lines': [{
                'id': 'partner_%s' % self.partner.id,
                'name': self.partner.display_name,
                'line_type': 'partner',
                'foldable': True,
                'partner_id': self.partner.id,
                'debit': 5200000.0,
                'credit': 0.0,
                'balance': 5200000.0,
                'children': [
                    {
                        'id': 'initial',
                        'name': 'Initial Balance',
                        'line_type': 'initial',
                        'debit': 0.0,
                        'credit': 0.0,
                        'balance': 0.0,
                        'children': [],
                    },
                    move_child,
                ],
            }, {
                'id': 'total',
                'name': 'Total',
                'line_type': 'total',
                'debit': 5200000.0,
                'credit': 0.0,
                'balance': 5200000.0,
                'children': [],
            }],
        }
        enriched = self.hook.enrich_partner_ledger_data(engine, fake)
        partner_line = enriched['lines'][0]
        types = [child.get('line_type') for child in partner_line['children']]
        self.assertIn('initial', types)
        self.assertIn('move_line', types)
        self.assertIn('opal', types)
        move = next(child for child in partner_line['children'] if child.get('id') == 'move_pjsbnk2')
        self.assertAlmostEqual(move['debit'], 3000000.0, places=2)
        self.assertAlmostEqual(move['credit'], 0.0, places=2)
        self.assertAlmostEqual(partner_line['balance'], 5200000.0 - 217897.0, places=2)
        self.assertAlmostEqual(enriched['lines'][-1]['balance'], 5200000.0 - 217897.0, places=2)

    def test_project_netting_subtracts_opal_from_odoo_balance(self):
        analytic = self._analytic('DEHARKI SUGAR MILLS')
        engine = PartnerLedgerEngine(self.env, {
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'target_move': 'posted',
            'partner_ids': [self.partner.id],
            'account_filters': ['payable'],
            'analytic_account_id': analytic.id,
            'show_opal_balance': True,
            'unfold_all': True,
        })
        # Pretend Odoo already built a 5.2M debit partner line; enrich must net OPAL.
        fake = {
            'lines': [{
                'id': 'partner_%s' % self.partner.id,
                'name': self.partner.display_name,
                'line_type': 'partner',
                'foldable': True,
                'partner_id': self.partner.id,
                'debit': 5200000.0,
                'credit': 0.0,
                'balance': 5200000.0,
                'children': self.hook.get_partner_children(
                    self.partner,
                    {
                        'show_opal_balance': True,
                        'analytic_account_id': analytic.id,
                    },
                    self.currency,
                ),
            }, {
                'id': 'total',
                'name': 'Total',
                'line_type': 'total',
                'debit': 5200000.0,
                'credit': 0.0,
                'balance': 5200000.0,
                'children': [],
            }],
        }
        enriched = self.hook.enrich_partner_ledger_data(engine, fake)
        partner_line = enriched['lines'][0]
        self.assertAlmostEqual(partner_line['debit'], 5200000.0, places=2)
        self.assertAlmostEqual(partner_line['credit'], 217897.0, places=2)
        self.assertAlmostEqual(partner_line['balance'], 5200000.0 - 217897.0, places=2)
        self.assertAlmostEqual(enriched['lines'][-1]['balance'], 5200000.0 - 217897.0, places=2)

    def test_unchecked_opal_ignores_project_filter_rows(self):
        analytic = self._analytic('DEHARKI SUGAR MILLS')
        rows = self.hook.get_partner_children(
            self.partner,
            {
                'show_opal_balance': False,
                'analytic_account_id': analytic.id,
            },
            self.currency,
        )
        self.assertFalse(rows)

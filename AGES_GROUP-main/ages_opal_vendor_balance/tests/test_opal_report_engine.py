# -*- coding: utf-8 -*-

from odoo.tests.common import tagged

from odoo.addons.ages_opal_vendor_balance.report.opal_report_engine import (
    OpalVendorBalanceEngine,
)

from .common import OpalVendorBalanceCase


@tagged('post_install', '-at_install')
class TestOpalReportEngine(OpalVendorBalanceCase):

    def _data(self, **options):
        return OpalVendorBalanceEngine(self.env, options).get_report_data()

    def test_search_abdul_rehman_four_lines_when_mapped(self):
        self._import_sample()
        partner = self.env['res.partner'].create({
            'name': 'ABDUL REHMAN CRUSH SUPPLIER',
            'supplier_rank': 1,
        })
        mapping = self.env['opal.vendor.map'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], limit=1)
        mapping.partner_id = partner
        data = self._data(tab='vendor_project', line_search='abdul rehman')
        lines = data['lines']
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0]['source'], 'odoo_overall')
        self.assertTrue(lines[0]['mapped'])
        self.assertEqual(lines[1]['source'], 'opal_overall')
        self.assertAlmostEqual(lines[1]['balance'], 11188325.0)
        self.assertEqual(lines[2]['project_code'], 'AG-SO-0017-24')
        self.assertEqual(lines[3]['project_code'], 'AG-SO-0028-26')
        self.assertAlmostEqual(lines[2]['balance'] + lines[3]['balance'], 11188325.0)

    def test_unmapped_vendor_keeps_odoo_line_flag(self):
        self._import_sample()
        mapping = self.env['opal.vendor.map'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], limit=1)
        mapping.partner_id = False
        data = self._data(tab='vendor_project', line_search='abdul rehman')
        lines = data['lines']
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0]['source'], 'odoo_overall')
        self.assertFalse(lines[0]['mapped'])
        self.assertEqual(sum(1 for line in lines if line['source'].startswith('opal')), 3)

    def test_project_filter_keeps_overall_plus_one_project(self):
        self._import_sample()
        data = self._data(
            tab='vendor_project',
            line_search='abdul rehman',
            project_codes=['AG-SO-0028-26'],
        )
        lines = data['lines']
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]['source'], 'odoo_overall')
        self.assertEqual(lines[1]['source'], 'opal_overall')
        self.assertAlmostEqual(lines[1]['balance'], 217897.0)
        self.assertEqual(lines[2]['project_code'], 'AG-SO-0028-26')

    def test_tab_two_has_no_odoo_overall(self):
        self._import_sample()
        data = self._data(tab='vendor_account', line_search='abdul rehman')
        self.assertTrue(data['lines'])
        self.assertFalse(any(line['source'] == 'odoo_overall' for line in data['lines']))
        self.assertTrue(all(line['source'] == 'opal_account' for line in data['lines']))

    def test_account_filter_shrinks_tab_one(self):
        self._import_sample()
        data = self._data(
            tab='vendor_project',
            account_names=['missing account'],
        )
        self.assertFalse(data['lines'])
        data = self._data(
            tab='vendor_project',
            line_search='nawaz',
            account_names=['07-01-001-0001 — CREDITOR FOR RAW MATERIAL'],
        )
        projects = [line for line in data['lines'] if line['source'] == 'opal_project']
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]['vendor'], 'NAWAZ SUPPLIER')

    def test_deharki_client_appears_in_report_and_filters(self):
        self._import_sample()
        data = self._data(tab='vendor_project', line_search='deharki sugar')
        names = [line['vendor'] for line in data['lines']]
        self.assertTrue(names)
        self.assertTrue(all(name == 'DEHARKI SUGAR MILLS' for name in names))
        opal = next(line for line in data['lines'] if line['source'] == 'opal_overall')
        self.assertAlmostEqual(opal['balance'], -37648784.0)
        filters = OpalVendorBalanceEngine(self.env, {'full_dataset': True}).get_filter_options()
        self.assertIn('DEHARKI SUGAR MILLS', filters['vendor_options'])
        self.assertIn('ABDUL REHMAN CRUSH SUPPLIER', filters['vendor_options'])

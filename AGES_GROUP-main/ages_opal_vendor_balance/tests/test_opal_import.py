# -*- coding: utf-8 -*-

import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from odoo.addons.ages_opal_vendor_balance.report.opal_xlsx_io import (
    SHEET_VENDOR_PROJECT,
    build_sample_workbook,
    build_workbook,
)

from .common import OpalVendorBalanceCase


@tagged('post_install', '-at_install')
class TestOpalImport(OpalVendorBalanceCase):

    def test_import_abdul_rehman_rows(self):
        self._import_sample()
        lines = self.env['opal.vendor.project'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], order='project_code')
        self.assertEqual(len(lines), 2)
        sindhri = lines.filtered(lambda rec: rec.project_code == 'AG-SO-0017-24')
        deharki = lines.filtered(lambda rec: rec.project_code == 'AG-SO-0028-26')
        self.assertAlmostEqual(sindhri.balance, 10970428.0)
        self.assertAlmostEqual(deharki.balance, 217897.0)
        self.assertAlmostEqual(sum(lines.mapped('balance')), 11188325.0)
        self.assertAlmostEqual(sum(lines.mapped('debit')), 62914900.0)
        self.assertAlmostEqual(sum(lines.mapped('credit')), 74103225.0)

    def test_import_includes_client_balances(self):
        record = self._import_sample()
        client = self.env['opal.vendor.project'].search([
            ('vendor_name', '=', 'DEHARKI SUGAR MILLS'),
            ('party_type', '=', 'client'),
        ])
        self.assertEqual(len(client), 1)
        self.assertEqual(client.project_code, 'AG-SO-0028-26')
        self.assertEqual(client.project_name, 'DEHARKI')
        self.assertAlmostEqual(client.balance, -37648784.0)
        names = self.env['opal.vendor.project'].search([]).mapped('vendor_name')
        self.assertIn('DEHARKI SUGAR MILLS', names)
        self.assertIn('ABDUL REHMAN CRUSH SUPPLIER', names)
        self.assertEqual(record.client_count, 1)
        self.assertEqual(record.vendor_count, 2)

    def test_second_import_replaces_client_rows(self):
        self._import_sample()
        self.env['opal.vendor.project'].create({
            'vendor_name': 'STALE CLIENT',
            'project_code': 'AG-SO-0000-00',
            'project_name': 'GONE',
            'party_type': 'client',
            'debit': 1.0,
            'credit': 0.0,
            'balance': 1.0,
            'currency_id': self.env.company.currency_id.id,
        })
        self._import_sample()
        self.assertFalse(self.env['opal.vendor.project'].search([
            ('vendor_name', '=', 'STALE CLIENT'),
        ]))
        self.assertTrue(self.env['opal.vendor.project'].search([
            ('vendor_name', '=', 'DEHARKI SUGAR MILLS'),
            ('party_type', '=', 'client'),
        ]))

    def test_client_only_workbook_is_rejected(self):
        data = build_workbook({
            'Client_by_Project': {
                'headers': ['Client', 'Project Code', 'Project Name', 'Debit', 'Credit', 'Balance'],
                'rows': [['DEHARKI SUGAR MILLS', 'AG-SO-0028-26', 'DEHARKI', 1, 2, -1]],
            },
        })
        record = self.env['opal.vendor.balance.import'].create({
            'data_file': base64.b64encode(data),
        })
        with self.assertRaises(UserError):
            record._process_import()

    def test_recomputed_vendor_total_matches_excel(self):
        self._import_sample()
        lines = self.env['opal.vendor.project'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ])
        self.assertEqual(len({line.project_code for line in lines}), 2)
        self.assertAlmostEqual(sum(lines.mapped('balance')), 11188325.0)

    def test_second_import_replaces_rows_and_keeps_maps(self):
        self._import_sample()
        mapping = self.env['opal.vendor.map'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], limit=1)
        mapping.notes = 'Keep me'
        first_count = self.env['opal.vendor.project'].search_count([])
        self.assertGreater(first_count, 0)
        self._import_sample()
        self.assertEqual(self.env['opal.vendor.project'].search_count([]), first_count)
        kept = self.env['opal.vendor.map'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], limit=1)
        self.assertEqual(kept.notes, 'Keep me')

    def test_bad_header_raises(self):
        data = build_workbook({
            SHEET_VENDOR_PROJECT: {
                'headers': ['Nope'],
                'rows': [['x']],
            },
            'Vendor_Project_Account': {'headers': ['Vendor'], 'rows': []},
            'Vendor_Totals': {'headers': ['Vendor'], 'rows': []},
            'Project_Totals': {'headers': ['Project Code'], 'rows': []},
            'Client_by_Project': {'headers': ['Client'], 'rows': []},
        })
        record = self.env['opal.vendor.balance.import'].create({
            'data_file': base64.b64encode(data),
        })
        with self.assertRaises(UserError):
            record._process_import()
        self.assertFalse(self.env['opal.vendor.project'].search([]))

    def test_invoice_user_cannot_import(self):
        user = self.env['res.users'].create({
            'name': 'OPAL Invoice User',
            'login': 'opal_invoice_user',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_invoice').id,
            ])],
        })
        data = build_sample_workbook()
        record = self.env['opal.vendor.balance.import'].create({
            'data_file': base64.b64encode(data),
        })
        with self.assertRaises((AccessError, UserError)):
            record.with_user(user)._process_import()

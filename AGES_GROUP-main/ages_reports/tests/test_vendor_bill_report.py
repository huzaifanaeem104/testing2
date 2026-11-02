# -*- coding: utf-8 -*-

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVendorBillReport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        parent = cls.env['stock.location'].search([
            ('company_id', '=', cls.env.company.id),
            ('usage', '=', 'internal'),
        ], limit=1)
        if not parent:
            parent = cls.env['stock.location'].create({
                'name': 'Bill Report Parent',
                'usage': 'internal',
                'company_id': cls.env.company.id,
            })
        cls.env.company.ages_default_parent_location_id = parent.id
        cls.sub_company = cls.env['ages.sub.company'].create({
            'name': 'Bill Report Active Co',
            'short_code': 'BRC',
            'company_id': cls.env.company.id,
        })
        project_vals = {
            'name': 'Pioneer Water Supply | Client',
            'partner_id': cls.partner_a.id,
        }
        if 'ages_sub_company_id' in cls.env['project.project']._fields:
            project_vals['ages_sub_company_id'] = cls.sub_company.id
        cls.project = cls.env['project.project'].create(project_vals)
        cls.contract = cls.env['ages.contract'].create({
            'partner_id': cls.partner_a.id,
            'project_id': cls.project.id,
            'sub_company_id': cls.sub_company.id,
            'company_id': cls.env.company.id,
            'contract_description': 'Dhadhar Project Mechanical Work Pioneer Cement Limited',
        })
        expense = cls.company_data['default_account_expense']
        cls.bill = cls.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': '2026-09-24',
            'ages_project_id': cls.project.id,
            'ages_contract_id': cls.contract.id,
            'ages_sub_company_id': cls.sub_company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'STEEL - BAR # 3',
                'quantity': 350.0,
                'price_unit': 256.0,
                'account_id': expense.id,
            })],
        })

    def test_print_bill_report_values_include_project_and_vendor(self):
        values = self.env['report.ages_reports.vendor_bill']._get_report_values(self.bill.ids)
        self.assertEqual(len(values['entries']), 1)
        entry = values['entries'][0]
        self.assertEqual(entry['vendor_name'], self.partner_a.display_name)
        self.assertIn('Pioneer Water Supply', entry['project_name'])
        self.assertIn('Dhadhar Project Mechanical Work', entry['contract_description'])
        self.assertEqual(entry['title'], 'Vendor Bill')
        self.assertEqual(len(entry['lines']), 1)
        self.assertAlmostEqual(entry['lines'][0]['qty'], 350.0)
        self.assertAlmostEqual(entry['lines'][0]['subtotal'], 89600.0)

    def test_print_bill_action_returns_report(self):
        report = self.env.ref('ages_reports.action_report_vendor_bill')
        self.assertEqual(report.report_name, 'ages_reports.vendor_bill')
        self.assertEqual(report.paperformat_id.orientation, 'Portrait')
        action = self.bill.with_context(discard_logo_check=True).action_print_bill()
        self.assertEqual(action.get('report_name'), 'ages_reports.vendor_bill')

    def test_print_bill_rejects_customer_invoice(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-09-24',
            'invoice_line_ids': [(0, 0, {
                'name': 'Client line',
                'quantity': 1,
                'price_unit': 10.0,
                'account_id': self.company_data['default_account_revenue'].id,
            })],
        })
        with self.assertRaises(UserError):
            invoice.action_print_bill()

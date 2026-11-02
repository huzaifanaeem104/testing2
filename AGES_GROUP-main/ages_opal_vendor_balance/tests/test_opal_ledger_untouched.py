# -*- coding: utf-8 -*-

from odoo.tests.common import tagged

from odoo.addons.ages_opal_vendor_balance.report.opal_report_engine import (
    OpalVendorBalanceEngine,
)

from .common import OpalVendorBalanceCase


@tagged('post_install', '-at_install')
class TestOpalLedgerUntouched(OpalVendorBalanceCase):

    def _snapshot(self):
        return {
            'moves': self.env['account.move'].search_count([]),
            'lines': self.env['account.move.line'].search_count([]),
            'partials': self.env['account.partial.reconcile'].search_count([]),
        }

    def test_import_and_report_do_not_write_ledgers(self):
        partner = self.env['res.partner'].create({
            'name': 'Ledger Guard Vendor',
            'supplier_rank': 1,
        })
        before = self._snapshot()
        self._import_sample()
        mapping = self.env['opal.vendor.map'].search([
            ('vendor_name', '=', 'ABDUL REHMAN CRUSH SUPPLIER'),
        ], limit=1)
        mapping.write({'partner_id': partner.id, 'notes': 'ledger guard'})
        project_map = self.env['opal.project.map'].search([], limit=1)
        if project_map:
            project_map.write({'project_name': project_map.project_name or 'SINDHRI'})
        wizard = self.env['opal.report.wizard'].create({
            'line_search': 'abdul rehman',
        })
        for tab in ('vendor_project', 'vendor_account', 'vendor_total', 'project_total'):
            OpalVendorBalanceEngine(self.env, {
                'tab': tab,
                'line_search': 'abdul rehman',
            }).get_report_data()
            wizard.get_report_data(wizard.id, {'tab': tab, 'line_search': 'abdul rehman'})
        after = self._snapshot()
        self.assertEqual(after['moves'], before['moves'])
        self.assertEqual(after['lines'], before['lines'])
        self.assertEqual(after['partials'], before['partials'])

    def test_invoice_user_can_read_report(self):
        self._import_sample()
        user = self.env['res.users'].create({
            'name': 'OPAL Reader',
            'login': 'opal_reader',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_invoice').id,
            ])],
        })
        lines = self.env['opal.vendor.project'].with_user(user).search([])
        self.assertTrue(lines)
        data = OpalVendorBalanceEngine(
            self.env(user=user),
            {'tab': 'vendor_project', 'line_search': 'abdul rehman'},
        ).get_report_data()
        self.assertTrue(data['lines'])

    def test_partner_ledger_opal_rows_only_when_checked(self):
        self._import_sample()
        partner = self.env['res.partner'].create({
            'name': 'ABDUL REHMAN CRUSH SUPPLIER | SINDHRI',
            'supplier_rank': 1,
        })
        hook = self.env['opal.partner.ledger.hook']
        off = hook.get_partner_children(partner, {'show_opal_balance': False}, self.env.company.currency_id)
        self.assertFalse(off)
        on = hook.get_partner_children(partner, {'show_opal_balance': True}, self.env.company.currency_id)
        self.assertTrue(on)
        self.assertEqual(on[0]['line_type'], 'opal')
        self.assertEqual(on[0]['name'], 'OPAL Overall')
        self.assertGreaterEqual(len(on), 3)

    def test_opal_checkbox_rows_do_not_write_ledgers(self):
        self._import_sample()
        partner = self.env['res.partner'].create({
            'name': 'ABDUL REHMAN CRUSH SUPPLIER',
            'supplier_rank': 1,
        })
        payable = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_ids', 'in', self.env.company.id),
        ], limit=1)
        before = self._snapshot()
        writes = {
            rec.id: rec.write_date
            for rec in self.env['account.move.line'].search([])
        }
        hook = self.env['opal.partner.ledger.hook']
        hook.get_partners_children_map(
            [partner], {'show_opal_balance': True}, self.env.company.currency_id
        )
        hook.get_partner_children(partner, {'show_opal_balance': True}, self.env.company.currency_id)
        if payable:
            hook.get_accounts_children_map(
                payable,
                {payable.id: [partner.id]},
                {'show_opal_balance': True},
                self.env.company.currency_id,
            )
            hook.get_account_children(
                payable, [partner.id], {'show_opal_balance': True}, self.env.company.currency_id
            )
        after = self._snapshot()
        self.assertEqual(after, before)
        for rec in self.env['account.move.line'].search([]):
            self.assertEqual(rec.write_date, writes.get(rec.id))

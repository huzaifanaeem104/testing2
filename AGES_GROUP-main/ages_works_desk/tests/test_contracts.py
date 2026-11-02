# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWorksContracts(TransactionCase):

    def test_remaining_ra_capacity_formula(self):
        partner = self.env['res.partner'].create({'name': 'Works Desk Client'})
        sub = self.env['ages.sub.company'].create({
            'name': 'Works Sub',
            'short_code': 'WDX',
            'company_id': self.env.company.id,
        })
        contract = self.env['ages.contract'].create({
            'partner_id': partner.id,
            'sub_company_id': sub.id,
            'company_id': self.env.company.id,
        })
        self.env['ages.contract.scope.line'].create({
            'contract_id': contract.id,
            'name': 'Main scope',
            'amount_before_rebate': 100000,
        })
        self.env.flush_all()
        contract.invalidate_recordset(['total_work_done_value'])
        self.assertEqual(contract.total_work_done_value, 100000)

        project = self.env['project.project'].with_context(ages_skip_auto_setup=True).create({
            'name': 'Works Desk Project',
            'partner_id': partner.id,
            'company_id': self.env.company.id,
            'ages_sub_company_id': sub.id,
        })
        contract.write({'state': 'running'})
        self.env['ages.running.bill'].create({
            'partner_id': partner.id,
            'contract_id': contract.id,
            'project_id': project.id,
            'company_id': self.env.company.id,
            'value_of_work_done': 40000,
        })
        self.env.flush_all()
        contract.invalidate_recordset(['running_bill_ids', 'running_bills_work_done', 'can_create_ra_bill'])

        remaining = self.env['ages.works.desk'].remaining_ra_capacity(contract)
        self.assertEqual(remaining, 60000)
        self.assertGreaterEqual(remaining, 0)

        payload = self.env['ages.works.desk'].get_contracts({
            'contract_ids': [contract.id],
            'selected_id': contract.id,
            'queue_key': 'remaining',
        })
        self.assertTrue(payload.get('ok'))
        row = next((r for r in payload['rows'] if r['id'] == contract.id), False)
        self.assertTrue(row)
        self.assertEqual(row['remaining_ra'], 60000)
        self.assertEqual(row['contract_value'], 100000)
        self.assertEqual(row['ra_work'], 40000)
        inspector = payload.get('inspector') or {}
        self.assertEqual(inspector.get('kind'), 'contract')
        self.assertEqual(inspector['amounts']['remaining_ra'], 60000)
        letters = [step['letter'] for step in inspector['waterfall']['steps']]
        self.assertEqual(letters, ['A', 'B', 'C', 'D', 'E', 'F', 'H', 'I'])

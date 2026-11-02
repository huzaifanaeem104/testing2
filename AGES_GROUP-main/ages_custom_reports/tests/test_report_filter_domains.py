# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase

from ..report.report_display import clip_project_name
from ..report.report_filter_domains import (
    analytic_reach_domain,
    journal_reach_domain,
    partner_reach_domain,
)


@tagged('post_install', '-at_install')
class TestReportFilterDomains(TransactionCase):

    def test_empty_filters_are_noop(self):
        self.assertEqual(journal_reach_domain(self.env, []), [])
        self.assertEqual(analytic_reach_domain(self.env, []), [])
        self.assertEqual(partner_reach_domain(self.env, []), [])

    def test_journal_reach_includes_default_account(self):
        journal = self.env['account.journal'].search(
            [('type', 'in', ('bank', 'cash')), ('default_account_id', '!=', False)],
            limit=1,
        )
        if not journal:
            self.skipTest('No bank/cash journal with a default account')
        domain = journal_reach_domain(self.env, [journal.id])
        self.assertTrue(domain)
        self.assertIn(('journal_id', 'in', [journal.id]), str(domain))
        self.assertIn(journal.default_account_id.id, str(domain))

    def test_analytic_reach_uses_json_in_operator(self):
        domain = analytic_reach_domain(self.env, [42])
        self.assertTrue(any(
            term == ('analytic_distribution', 'in', [42])
            for term in domain
            if isinstance(term, (list, tuple))
        ))

    def test_partner_reach_includes_partner_id(self):
        domain = partner_reach_domain(self.env, [7])
        self.assertTrue(any(
            term == ('partner_id', 'in', [7])
            for term in domain
            if isinstance(term, (list, tuple))
        ))

    def test_clip_project_name_drops_repeated_role_suffix(self):
        self.assertEqual(
            clip_project_name(
                'DEHARKI SUGAR MILLS | CLIENT | - DEHARKI SUGAR MILLS | CLIENT |'
            ),
            'DEHARKI SUGAR MILLS',
        )

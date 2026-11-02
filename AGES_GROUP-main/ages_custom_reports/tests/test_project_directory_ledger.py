# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase

from ..report.project_directory_ledger_common import (
    primary_analytic_id_from_distribution,
)


@tagged('post_install', '-at_install')
class TestProjectDirectoryLedgerMapping(TransactionCase):

    def test_line_uses_its_own_analytic_not_first_dict_key(self):
        distribution = {'11': 1.13, '22': 98.87}
        self.assertEqual(primary_analytic_id_from_distribution(distribution), 22)

    def test_no_analytic_is_uncategorized(self):
        self.assertFalse(primary_analytic_id_from_distribution(False))
        self.assertFalse(primary_analytic_id_from_distribution({}))
        self.assertFalse(primary_analytic_id_from_distribution({'11': 0}))

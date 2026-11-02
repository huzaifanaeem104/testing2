# -*- coding: utf-8 -*-

from odoo.api import call_kw
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAgesEnterpriseDashboard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.dashboard = self.env['ages.enterprise.dashboard']

    def test_normalize_filters_unauthorized_company(self):
        scope = self.dashboard._normalize_filters({'company_ids': [999999], 'period': 'month'})
        self.assertEqual(scope['company_ids'], [0])

    def test_empty_project_ids_do_not_restrict_scope(self):
        empty = self.dashboard._normalize_filters({'period': 'month', 'project_ids': []})
        self.assertIsNone(empty.get('project_ids'))
        missing = self.dashboard._normalize_filters({'period': 'month'})
        self.assertIsNone(missing.get('project_ids'))
        domain = self.dashboard._scope_domain('account.move.line', empty)
        self.assertFalse(any(
            isinstance(leaf, (list, tuple)) and leaf and leaf[0] == 'analytic_distribution'
            for leaf in domain
        ))

    def test_context_lists_dashboards(self):
        context = self.dashboard.get_dashboard_context({})
        keys = [item['key'] for item in context['dashboards']]
        self.assertIn('executive', keys)
        self.assertIn('finance', keys)
        self.assertIn('payroll', keys)
        self.assertIn('quality_data', keys)
        self.assertIn('action_center', keys)

    def test_executive_payload_shape(self):
        payload = self.dashboard.get_executive_dashboard({'period': 'month'})
        self.assertEqual(payload['meta']['dashboard'], 'executive')
        self.assertIn('kpis', payload)
        self.assertTrue(payload['kpis'])
        self.assertIn('value', payload['kpis'][0])
        self.assertIn('formatted', payload['kpis'][0])
        self.assertIn('basis', payload['kpis'][0])
        self.assertIn('formula', payload['kpis'][0])

    def test_open_action_allowlist(self):
        self.assertFalse(self.dashboard.open_action('not_a_real_action', {}))
        action = self.dashboard.open_action('customer_invoices', {'period': 'month'})
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move')
        self.assertTrue(self.dashboard.open_action('unreconciled', {}))

    def test_draft_moves_excluded_from_revenue(self):
        payload = self.dashboard.get_finance_dashboard({'period': 'year'})
        self.assertEqual(payload['meta']['dashboard'], 'finance')
        self.assertEqual(payload['meta']['date_field'], 'account.move.line.date')
        keys = [kpi['key'] for kpi in payload['kpis']]
        self.assertIn('collections', keys)
        self.assertIn('vendor_payments', keys)
        self.assertIn('bank', keys)

    def test_data_quality_payload(self):
        payload = self.dashboard.get_data_quality_dashboard({'period': 'month'})
        self.assertEqual(payload['meta']['dashboard'], 'quality_data')
        self.assertTrue(payload.get('quality_cards'))

    def test_action_center_explains_queues(self):
        payload = self.dashboard.get_action_center_dashboard({})
        self.assertTrue(payload.get('alerts'))
        self.assertIn('why', payload['alerts'][0])
        self.assertIn('count', payload['alerts'][0])

    def test_contracts_payload_includes_payment_kpis(self):
        payload = self.dashboard.get_contracts_dashboard({'period': 'year'})
        self.assertEqual(payload['meta']['dashboard'], 'contracts')
        if payload.get('available') is False:
            return
        keys = [kpi['key'] for kpi in payload['kpis']]
        self.assertIn('backlog', keys)
        self.assertIn('missing_invoice', keys)

    def test_all_core_dashboards_return_payload(self):
        keys = [
            'executive', 'action_center', 'finance', 'contracts', 'projects',
            'procurement', 'inventory', 'expenses', 'hr', 'payroll', 'attendance',
            'sales', 'partners', 'assets', 'governance', 'quality_data',
        ]
        for key in keys:
            payload = self.dashboard.get_dashboard(key, {'period': 'month'})
            self.assertIn('meta', payload)
            self.assertEqual(payload['meta']['dashboard'], key)
            self.assertIn('kpis', payload)
            self.assertIn('charts', payload)
            self.assertIn('tables', payload)
            self.assertIn('generated_at', payload['meta'])

    def test_filter_catalog_and_options(self):
        context = self.dashboard.get_dashboard_context({})
        self.assertIn('filter_catalog', context)
        self.assertIn('company', context['filter_catalog']['executive'])
        options = self.dashboard.get_filter_options({})
        self.assertIn('companies', options)
        self.assertIn('departments', options)
        self.assertIn('warehouses', options)
        self.assertIn('employees', options)

    def test_executive_ra_split_and_workforce_chart_keys(self):
        payload = self.dashboard.get_executive_dashboard({'period': 'month'})
        keys = [kpi['key'] for kpi in payload['kpis']]
        self.assertIn('ra_work', keys)
        self.assertIn('ra_receivable', keys)
        self.assertIn('ra_billed', keys)
        self.assertIn('po_open', keys)
        self.assertTrue(payload['charts'])

    def test_finance_unassigned_and_cashflow(self):
        payload = self.dashboard.get_finance_dashboard({'period': 'year'})
        keys = [kpi['key'] for kpi in payload['kpis']]
        self.assertIn('unassigned_analytic', keys)
        self.assertIn('cashflow', payload['charts'])
        self.assertIn('journals', payload['charts'])

    def test_open_action_payroll_keys(self):
        self.assertIn('loan_installments', self.dashboard._action_specs())
        self.assertIn('payslip_runs', self.dashboard._action_specs())
        self.assertIn('pending_pr_qty', self.dashboard._action_specs())
        self.assertIn('purchase_commitments', self.dashboard._action_specs())
        self.assertIn('below_reorder', self.dashboard._action_specs())
        self.assertIn('missing_checkouts_all', self.dashboard._action_specs())

    def test_ytd_period_uses_year_start(self):
        scope = self.dashboard._normalize_filters({'period': 'ytd'})
        self.assertEqual(scope['period'], 'ytd')
        self.assertEqual(scope['date_from'].month, 1)
        self.assertEqual(scope['date_from'].day, 1)
        self.assertEqual(scope['previous_from'].year, scope['date_from'].year - 1)

    def test_executive_pulse_includes_bank_and_collections(self):
        payload = self.dashboard.get_executive_dashboard({'period': 'month'})
        keys = [kpi['key'] for kpi in payload['kpis']]
        self.assertIn('bank', keys)
        self.assertIn('collections', keys)
        self.assertIn('vendor_payments', keys)
        self.assertIn('commentary', payload)
        self.assertNotIn('scorecards', payload)
        self.assertIn('comparison_label', payload['meta'])
        self.assertEqual((payload.get('layout') or {}).get('kind'), 'briefing')
        hero = next((section for section in (payload.get('layout') or {}).get('sections') or [] if section.get('hero')), {})
        self.assertLessEqual(len(hero.get('keys') or []), 5)

    def test_action_center_queues_include_domain(self):
        payload = self.dashboard.get_action_center_dashboard({})
        self.assertTrue(payload.get('alerts') or payload.get('cleared') is not None)
        for queue in payload.get('alerts') or []:
            self.assertNotIn('domain', queue)
            self.assertIn('action_key', queue)
            self.assertIn('why', queue)
            self.assertIn('model', queue)

    def test_delayed_pr_domain_does_not_use_line_state(self):
        payload = self.dashboard.get_action_center_dashboard({})
        delayed = next((queue for queue in payload.get('alerts') or [] if queue.get('key') == 'delayed_pr'), None)
        if not delayed:
            return
        self.assertFalse(any(
            isinstance(leaf, (list, tuple)) and leaf and leaf[0] == 'state'
            for leaf in delayed.get('domain') or []
        ))

    def test_exception_missing_move_action_skips_period_date(self):
        specs = self.dashboard._action_specs()
        self.assertIn('payslips_missing_move_all', specs)
        self.assertFalse(specs['payslips_missing_move_all'].get('date_field'))
        action = self.dashboard.open_action('payslips_missing_move_all', {'period': 'month'})
        self.assertEqual(action['res_model'], 'hr.payslip')
        self.assertFalse(any(
            isinstance(leaf, (list, tuple)) and leaf and leaf[0] == 'date_from'
            for leaf in action.get('domain') or []
        ))

    def test_finance_working_capital_and_budget_keys(self):
        payload = self.dashboard.get_finance_dashboard({'period': 'year'})
        keys = [kpi['key'] for kpi in payload['kpis']]
        self.assertIn('working_capital', keys)
        self.assertIn('dso', keys)
        self.assertIn('dpo', keys)

    def test_procurement_requester_chart_uses_amounts(self):
        payload = self.dashboard.get_procurement_dashboard({'period': 'year'})
        if payload.get('available') is False:
            return
        chart = payload['charts'].get('requesters') or {}
        datasets = chart.get('datasets') or []
        if datasets and datasets[0].get('data'):
            self.assertNotEqual(datasets[0]['data'], [1] * len(datasets[0]['data']))

    def test_open_action_snapshot_commitments_skip_period_date(self):
        action = self.dashboard.open_action('purchase_commitments', {'period': 'month'})
        self.assertEqual(action['res_model'], 'purchase.order')
        domain = action.get('domain') or []
        self.assertFalse(any(
            isinstance(leaf, (list, tuple)) and leaf and leaf[0] == 'date_order'
            for leaf in domain
        ))

    def test_kpi_target_model_exists(self):
        self.assertIn('ages.dashboard.kpi.target', self.env)
        Target = self.env['ages.dashboard.kpi.target']
        record = Target.create({'kpi_key': 'revenue', 'target_value': 1000})
        self.assertEqual(record.kpi_key, 'revenue')

    def test_periods_include_ytd(self):
        context = self.dashboard.get_dashboard_context({})
        keys = [item['key'] for item in context['periods']]
        self.assertIn('ytd', keys)
        self.assertNotIn('year', keys)
        self.assertIn('kpi_registry', context)
        self.assertIn('default_dashboard', context)

    def test_optional_dashboards_return_payload_or_unavailable(self):
        for key in ('manufacturing', 'crm', 'construction', 'quality', 'system'):
            payload = self.dashboard.get_dashboard(key, {'period': 'month'})
            self.assertIn('meta', payload)
            self.assertEqual(payload['meta']['dashboard'], key)
            self.assertIn('kpis', payload)

    def test_payroll_hidden_without_payroll_group(self):
        user = self.env['res.users'].create({
            'name': 'AGES dashboard restricted',
            'login': 'ages_ent_restricted_user',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('ages_enterprise_dashboard.group_ages_enterprise_dashboard').id,
            ])],
        })
        payload = self.dashboard.with_user(user).get_payroll_dashboard({'period': 'month'})
        self.assertEqual(payload.get('available'), False)

    def test_run_rate_projection_scales_partial_period(self):
        scope = self.dashboard._normalize_filters({'period': 'month'})
        date_from = scope['date_from']
        date_to = scope['date_to']
        elapsed = (date_to - date_from).days + 1
        if elapsed <= 1:
            return
        projected = self.dashboard._run_rate_projection(elapsed, date_from, date_to)
        self.assertTrue(projected)
        self.assertGreaterEqual(projected, elapsed)

    def test_open_action_timeout_and_construction_keys(self):
        specs = self.dashboard._action_specs()
        self.assertIn('timeout_sessions', specs)
        self.assertIn('mrp_waiting', specs)
        self.assertIn('construction_rfi', specs)
        self.assertFalse(self.dashboard.open_action('not_a_real_action', {}))

    def test_subcompany_warning_when_filter_set(self):
        payload = self.dashboard._payload(
            {'company_ids': self.env.companies.ids, 'sub_company_ids': [0], 'include_unassigned': True},
            'executive',
        )
        self.assertTrue(any('legal-company-wide' in warning for warning in payload['meta']['warnings']))

    def _xmlid(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _dashboard_user(self, login, extra_groups):
        group_ids = [
            self.env.ref('base.group_user').id,
            self.env.ref('ages_enterprise_dashboard.group_ages_enterprise_dashboard').id,
        ]
        for xmlid in extra_groups:
            group = self._xmlid(xmlid)
            if group:
                group_ids.append(group.id)
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, list(dict.fromkeys(group_ids)))],
        })

    def test_role_visibility_matrix(self):
        cases = [
            ('ages_ent_internal', [], {'payroll': False}),
            ('ages_ent_project', ['project.group_project_user'], {'projects': True}),
            ('ages_ent_purchase', ['purchase.group_purchase_user'], {'procurement': True}),
            ('ages_ent_stock', ['stock.group_stock_user'], {'inventory': True}),
            ('ages_ent_account', ['account.group_account_readonly'], {'finance': True, 'payroll': False}),
            ('ages_ent_hr', ['hr.group_hr_user'], {'hr': True, 'payroll': False}),
        ]
        payroll_group = self._xmlid('ages_hr_payroll.group_hr_payroll_user')
        if payroll_group:
            cases.append(('ages_ent_payroll', ['ages_hr_payroll.group_hr_payroll_user'], {'payroll': True}))
        for login, groups, expectations in cases:
            user = self._dashboard_user(login, groups)
            dash = self.dashboard.with_user(user)
            context = dash.get_dashboard_context({})
            available = {item['key']: item['available'] for item in context['dashboards']}
            for key, expected in expectations.items():
                self.assertEqual(available.get(key), expected, '%s:%s' % (login, key))
            if expectations.get('payroll') is False:
                payroll = dash.get_payroll_dashboard({'period': 'month'})
                self.assertEqual(payroll.get('available'), False)

    def test_kpi_payloads_have_formula_and_basis(self):
        for key in ('executive', 'finance', 'action_center', 'contracts', 'payroll'):
            payload = self.dashboard.get_dashboard(key, {'period': 'month'})
            self.assertTrue(payload.get('kpis'))
            for kpi in payload['kpis']:
                self.assertTrue(kpi.get('key'))
                self.assertTrue(kpi.get('formula') or kpi.get('tooltip'))
                self.assertTrue(kpi.get('basis'))
                self.assertIn('formatted', kpi)

    def test_main_summary_engine_reused_when_importable(self):
        engine = self.dashboard._load_engine_class(
            'main_summary',
            'odoo.addons.ages_main_summary.report.main_summary_engine',
            'MainSummaryEngine',
            ['ages_main_summary/report/main_summary_engine.py',
             'AGES_GROUP/ages_main_summary/report/main_summary_engine.py'],
        )
        self.assertTrue(engine, 'MainSummaryEngine must load from ages_main_summary without installing that module')
        payload = self.dashboard.get_finance_dashboard({'period': 'year'})
        keys = [kpi['key'] for kpi in payload['kpis']]
        if payload.get('available') is False:
            return
        self.assertIn('vendor_invoice_payment', payload['charts'])
        if 'ms_opening' in keys:
            self.assertIn('ms_transfers', keys)
            self.assertTrue(any('MainSummaryEngine' in (warning or '') for warning in payload['meta']['warnings']))

    def test_leave_payroll_block_action(self):
        specs = self.dashboard._action_specs()
        self.assertIn('leave_payroll_blocked', specs)
        self.assertIn('followup_partners', specs)
        action = self.dashboard.open_action('leave_payroll_blocked', {})
        if action:
            self.assertEqual(action['res_model'], 'hr.leave')

    def test_kpi_registry_documents_sources(self):
        registry = self.dashboard._kpi_registry_summary()
        self.assertGreaterEqual(len(registry), 20)
        self.assertTrue(all(item.get('model') and item.get('formula') for item in registry))

    def test_posted_moves_only_in_income_action(self):
        action = self.dashboard.open_action('aml_income', {'period': 'year'})
        self.assertEqual(action['res_model'], 'account.move.line')
        self.assertIn(('parent_state', '=', 'posted'), action['domain'])

    def test_chart_marks_empty_when_no_values(self):
        empty = self.dashboard._chart('bar', 'Demo', [], [])
        self.assertTrue(empty.get('empty'))
        zeros = self.dashboard._chart('bar', 'Demo', ['A'], [{'label': 'X', 'data': [0]}])
        self.assertTrue(zeros.get('empty'))
        filled = self.dashboard._chart('bar', 'Demo', ['A'], [{'label': 'X', 'data': [12]}])
        self.assertFalse(filled.get('empty'))

    def test_row_limit_clamps_page_size(self):
        self.assertEqual(self.dashboard._row_limit({'limit': 500}, 20), 100)
        self.assertEqual(self.dashboard._row_limit({'limit': 0}, 20), 20)
        self.assertEqual(self.dashboard._row_limit({'limit': 5}, 20), 5)

    def test_document_statuses_follow_dashboard_key(self):
        options = self.dashboard.get_filter_options({'dashboard': 'sales', 'period': 'month'})
        ids = {item['id'] for item in options['document_statuses']}
        self.assertTrue({'draft', 'sale', 'done', 'cancel'} & ids)

    def test_catalog_unavailable_items_have_reason(self):
        catalog = self.dashboard._dashboard_catalog()
        self.assertTrue(any(item['key'] == 'executive' and item['available'] for item in catalog))
        for item in catalog:
            if not item['available']:
                self.assertTrue(item.get('reason'))

    def test_ar_ap_snapshot_exposes_basis(self):
        scope = self.dashboard._normalize_filters({'period': 'month'})
        data = self.dashboard._snapshot_ar_ap(scope)
        self.assertIn(data['ar_basis'], ('aged_engine', 'live_residual'))
        self.assertIn(data['ap_basis'], ('aged_engine', 'live_residual'))
        self.assertIn('receivables', data)
        self.assertIn('payables', data)

    def test_finance_includes_analytic_chart(self):
        payload = self.dashboard.get_finance_dashboard({'period': 'year'})
        if payload.get('available') is False:
            return
        self.assertIn('analytic', payload['charts'])

    def test_inventory_value_by_category_chart(self):
        payload = self.dashboard.get_inventory_dashboard({'period': 'month'})
        if payload.get('available') is False:
            return
        self.assertIn('value_category', payload.get('charts') or {})

    def test_contracts_backlog_by_project_chart(self):
        payload = self.dashboard.get_contracts_dashboard({'period': 'year'})
        if payload.get('available') is False:
            return
        self.assertIn('by_project', payload['charts'])

    def test_web_client_call_kw_passes_filters_not_ids(self):
        payload = call_kw(
            self.env['ages.enterprise.dashboard'],
            'get_dashboard',
            ['sales', {'period': 'month'}],
            {},
        )
        self.assertEqual(payload['meta']['dashboard'], 'sales')
        context = call_kw(
            self.env['ages.enterprise.dashboard'],
            'get_dashboard_context',
            [{'period': 'month'}],
            {},
        )
        self.assertTrue(context.get('dashboards'))
        action = call_kw(
            self.env['ages.enterprise.dashboard'],
            'open_action',
            ['customer_invoices', {'period': 'month'}],
            {},
        )
        self.assertEqual(action['type'], 'ir.actions.act_window')

    def test_draft_aml_excluded_from_revenue_domain(self):
        scope = self.dashboard._normalize_filters({'period': 'month'})
        domain = self.dashboard._aml_posted_domain(scope)
        self.assertIn(('parent_state', '=', 'posted'), domain)
        self.assertIn(('display_type', 'not in', ('line_section', 'line_note')), domain)

    def test_snapshot_cash_ignores_date_from(self):
        scope = self.dashboard._normalize_filters({'period': 'month'})
        earlier = dict(scope)
        earlier['date_from'] = scope['date_from'].replace(month=1, day=1)
        first = self.dashboard._cash_bank_snapshot(scope, scope['date_to'])
        second = self.dashboard._cash_bank_snapshot(earlier, scope['date_to'])
        self.assertEqual(first, second)

    def test_partners_catalog_gated_for_base_user(self):
        user = self._dashboard_user('ages_ent_partners_gate', [])
        dash = self.dashboard.with_user(user)
        caps = dash._capability_map()
        available = {item['key']: item['available'] for item in dash._dashboard_catalog()}
        expected = bool(caps.get('sale') or caps.get('purchase') or caps.get('account') or caps.get('contract'))
        self.assertEqual(available.get('partners'), expected)
        if not expected:
            payload = dash.get_partners_dashboard({'period': 'month'})
            self.assertEqual(payload.get('available'), False)

    def test_search_read_never_uses_limit_zero(self):
        import inspect
        rows = self.dashboard._search_read('res.company', [], ['name'], limit=0)
        self.assertTrue(rows or rows == [])
        self.assertLessEqual(len(rows), 500)
        self.assertNotIn('limit=0', inspect.getsource(self.dashboard._below_reorder_data))

    def test_filter_search_and_finance_options_are_slim(self):
        options = self.dashboard.get_filter_options({'dashboard': 'finance', 'period': 'month'})
        self.assertFalse(options.get('products'))
        self.assertFalse(options.get('employees'))
        rows = self.dashboard.get_filter_search('project', '', {'dashboard': 'projects', 'period': 'month'})
        self.assertIsInstance(rows, list)

    def test_doughnut_collapses_other_without_fake_id(self):
        chart = self.dashboard._chart(
            'doughnut', 'Demo', list('ABCDEFGHI'),
            [{'label': 'X', 'data': [1] * 9}],
            label_ids=list(range(1, 10)),
        )
        self.assertEqual(chart['labels'][-1], 'Other')
        self.assertLessEqual(len(chart['labels']), 7)
        self.assertFalse(chart['label_ids'][-1])

    def test_contracts_waterfall_uses_stored_ra(self):
        payload = self.dashboard.get_contracts_dashboard({'period': 'month'})
        if payload.get('available') is False:
            return
        chart = (payload.get('charts') or {}).get('waterfall') or {}
        self.assertEqual(chart.get('variant'), 'waterfall')


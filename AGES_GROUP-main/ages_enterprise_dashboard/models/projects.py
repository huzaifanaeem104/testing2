# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesEnterpriseDashboardProjects(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_projects_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._capability_map().get('project'):
            return self._unavailable(scope, 'projects', 'Project user or manager access is required.')
        domain = self._scope_domain('project.project', scope)
        date_from, date_to = scope['date_from'], scope['date_to']
        total = self._search_count('project.project', domain)
        active = self._search_count('project.project', domain + [('active', '=', True)])
        completed = 0
        if self._has_field('project.project', 'stage_id'):
            completed = self._search_count('project.project', domain + [('stage_id.fold', '=', True)]) if self._field_path_exists('project.project', 'stage_id.fold') else 0
        tasks_total = tasks_open = tasks_done = tasks_overdue = 0
        if self._can_read('project.task'):
            task_domain = self._scope_domain('project.task', scope)
            tasks_total = self._search_count('project.task', task_domain)
            tasks_open = self._search_count('project.task', task_domain + [('state', 'not in', ('1_done', '1_canceled'))])
            tasks_done = self._search_count('project.task', task_domain + [('state', '=', '1_done')])
            today = fields.Date.context_today(self)
            if self._has_field('project.task', 'date_deadline'):
                tasks_overdue = self._search_count('project.task', task_domain + [
                    ('date_deadline', '<', today),
                    ('state', 'not in', ('1_done', '1_canceled')),
                ])

        income_extra = [('account_id.account_type', 'in', ('income', 'income_other'))]
        expense_extra = [('account_id.account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))]
        cash_extra = [('account_id.account_type', '=', 'asset_cash')]
        revenue = self._analytic_project_total(scope, income_extra, date_from, date_to, invert=True)
        cost = self._analytic_project_total(scope, expense_extra, date_from, date_to)
        main_summary = self._main_summary_payload(scope)
        cash = False
        if main_summary and main_summary.get('kpis'):
            summary_kpis = main_summary['kpis']
            cash = (
                (summary_kpis.get('received') or 0.0)
                - (summary_kpis.get('expenses') or 0.0)
                + (summary_kpis.get('transfers') or 0.0)
            )
        coverage = self._analytic_coverage(scope, date_from, date_to)
        unassigned_cost = abs(self._aml_sum(scope, expense_extra + [('analytic_distribution', '=', False)], date_from, date_to) or 0.0)
        unassigned_rev = abs(self._aml_sum(scope, income_extra + [('analytic_distribution', '=', False)], date_from, date_to, invert=True) or 0.0)

        contract_value = ra_amount = ra_work = backlog = 0.0
        if self._can_read('ages.contract'):
            contract_value = self._read_group_sum('ages.contract', self._scope_domain('ages.contract', scope), 'total_work_done_value')
        if self._can_read('ages.running.bill'):
            ra_domain = self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')]) + self._date_domain('date', date_from, date_to)
            ra_amount = self._read_group_sum('ages.running.bill', ra_domain, 'net_amount')
            ra_work = self._read_group_sum('ages.running.bill', ra_domain, 'value_of_work_done')
            billed = self._read_group_sum(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [('state', '!=', 'cancelled')]),
                'value_of_work_done',
            )
            backlog = max((contract_value or 0.0) - (billed or 0.0), 0.0)
        po_open = 0.0
        if self._can_read('purchase.order'):
            po_open = self._read_group_sum(
                'purchase.order',
                self._scope_domain('purchase.order', scope, [
                    ('state', 'in', ('purchase', 'done')),
                    ('invoice_status', 'in', ('no', 'to invoice')),
                ]),
                'amount_untaxed',
            )
        consumption = 0.0
        if self._can_read('ages.material.consumption'):
            consumption = self._read_group_sum(
                'ages.material.consumption',
                self._scope_domain('ages.material.consumption', scope, [('state', '=', 'done')]) + self._date_domain('date', date_from, date_to),
                'amount_total',
            )
        payroll_cost = 0.0
        if self._capability_map().get('payroll') and self._has_field('hr.payslip', 'project_id'):
            payroll_cost = self._read_group_sum(
                'hr.payslip',
                self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))]) + self._date_domain('date_from', date_from, date_to),
                'net_wage',
            )
        att_hours = 0.0
        att_people = 0
        if self._can_read('hr.attendance') and self._has_field('hr.attendance', 'worked_hours'):
            att_domain = self._scope_domain('hr.attendance', scope)
            att_domain += self._datetime_date_domain('check_in', date_from, date_to)
            att_hours = self._read_group_sum('hr.attendance', att_domain, 'worked_hours')
            att_people = len({row.get('employee_id') and row['employee_id'][0] for row in self._search_read('hr.attendance', att_domain, ['employee_id'], limit=5000) if row.get('employee_id')})
        receivables = 0.0
        if self._can_read('account.move'):
            receivables = self._read_group_sum(
                'account.move',
                self._scope_domain('account.move', scope, [
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                    ('state', '=', 'posted'),
                ]),
                'amount_residual_signed',
            )

        kpis = [
            self._kpi(scope, 'projects', 'Projects', total, False, 'projects', suffix='', basis='count'),
            self._kpi(scope, 'active', 'Active projects', active, False, 'projects', suffix='', basis='count'),
            self._kpi(scope, 'completed', 'Folded/completed stages', completed, False, 'projects',
                      'Count of projects whose stage is folded, when stage_id.fold exists.', suffix='', basis='count'),
            self._kpi(scope, 'tasks', 'Tasks', tasks_total, False, 'project_tasks', suffix='', basis='count'),
            self._kpi(scope, 'tasks_open', 'Open tasks', tasks_open, False, 'project_tasks', suffix='', basis='count'),
            self._kpi(scope, 'tasks_done', 'Completed tasks', tasks_done, False, 'project_tasks', suffix='', basis='count'),
            self._kpi(scope, 'overdue_tasks', 'Overdue tasks', tasks_overdue, False, 'overdue_tasks', suffix='', basis='count'),
            self._kpi(scope, 'contract_value', 'Project contract value', contract_value, False, 'contracts',
                      'SUM(ages.contract.total_work_done_value) in project scope.'),
            self._kpi(scope, 'ra', 'RA billed (net)', ra_amount, False, 'running_bills'),
            self._kpi(scope, 'ra_work', 'RA work this period', ra_work, False, 'running_bills'),
            self._kpi(scope, 'backlog', 'Unbilled contract work', backlog, False, 'contracts'),
            self._kpi(scope, 'revenue', 'Recorded project revenue', revenue, False, 'aml_income',
                      'Posted income AML in scope. Analytic/project filters apply when present.',
                      basis='flow', date_field='account.move.line.date'),
            self._kpi(scope, 'cost', 'Recorded project cost', cost, False, 'aml_expense'),
            self._kpi(scope, 'margin', 'Recorded project margin', revenue - cost, False, False,
                      'Not complete project profit unless analytic coverage is complete.'),
            self._kpi(scope, 'unassigned_rev', 'Unassigned analytic income', unassigned_rev, False, 'aml_income'),
            self._kpi(scope, 'unassigned_cost', 'Unassigned analytic cost', unassigned_cost, False, 'aml_expense'),
            self._kpi(scope, 'po_open', 'Open purchase commitment', po_open, False, 'purchase_orders'),
            self._kpi(scope, 'consumption', 'Material consumption', consumption, False, 'material_consumption'),
            self._kpi(scope, 'payroll', 'Project payroll net', payroll_cost, False, 'payslips'),
            self._kpi(scope, 'att_hours', 'Attendance hours', att_hours, False, 'attendances', suffix='', basis='count'),
            self._kpi(scope, 'att_people', 'Employees with attendance', att_people, False, 'attendances', suffix='', basis='count'),
            self._kpi(scope, 'receivables', 'Project receivables', receivables, False, 'customer_invoices'),
            self._kpi(scope, 'cash', 'Project cash movement', cash, False, False,
                      'MainSummaryEngine period receipts minus expenses plus transfers. Snapshot cash is on Finance.') if cash is not False else self._unavailable_kpi(
                          scope, 'cash', 'Project cash movement',
                          'MainSummaryEngine is unavailable; direct cash-line analytics would omit its verified sibling/fallback allocation rules.',
                      ),
        ]
        labels, revenue_trend = self._monthly_analytic_project_trend(scope, income_extra, invert=True)
        _labels, cost_trend = self._monthly_analytic_project_trend(scope, expense_extra)
        contract_positions = self._project_contract_positions(scope)
        charts = {
            'pnl': self._chart('mixed', 'Recorded revenue vs cost vs margin', labels, [
                {'label': 'Revenue', 'data': revenue_trend},
                {'label': 'Cost', 'data': cost_trend},
                {'label': 'Margin', 'data': [round(rev - exp, 2) for rev, exp in zip(revenue_trend, cost_trend)], 'type': 'line'},
            ]),
            'backlog': self._chart('bar', 'Contract vs RA vs backlog', ['Contract value', 'Period RA work', 'Backlog'], [
                {'label': 'Amount', 'data': [round(contract_value or 0.0, 2), round(ra_work or 0.0, 2), round(backlog, 2)]},
            ]),
            'contract_projects': self._chart(
                'bar', 'Contract value vs cumulative RA vs backlog by project',
                [row['name'] for row in contract_positions],
                [
                    {'label': 'Contract value', 'data': [row['contract_raw'] for row in contract_positions]},
                    {'label': 'Cumulative RA', 'data': [row['ra_raw'] for row in contract_positions]},
                    {'label': 'Backlog', 'data': [row['backlog_raw'] for row in contract_positions]},
                ],
            ),
            'procurement': self._chart('bar', 'Purchase commitment vs material consumed', ['Open PO', 'Consumption'], [
                {'label': 'Amount', 'data': [round(po_open or 0.0, 2), round(consumption or 0.0, 2)]},
            ]),
            'tasks': self._chart('doughnut', 'Tasks completed vs open', ['Open', 'Done', 'Overdue'], [
                {'label': 'Tasks', 'data': [tasks_open, tasks_done, tasks_overdue]},
            ]),
        }
        if self._has_field('project.project', 'stage_id'):
            charts['stages'] = self._group_chart('project.project', domain + [('active', '=', True)], 'stage_id', 'Projects by stage')
        if self._can_read('hr.employee') and self._has_field('hr.employee', 'project_id'):
            charts['workforce'] = self._group_chart(
                'hr.employee', self._scope_domain('hr.employee', scope) + [('active', '=', True)],
                'project_id', 'Workforce by project',
            )
        overdue_task_rows = []
        if self._can_read('project.task'):
            overdue_task_rows = self._document_rows(
                'project.task',
                self._scope_domain('project.task', scope) + [
                    ('date_deadline', '<', fields.Date.context_today(self)),
                    ('state', 'not in', ('1_done', '1_canceled')),
                ] if self._has_field('project.task', 'date_deadline') else [('id', '=', 0)],
                {'name': 'name', 'deadline': 'date_deadline', 'project': 'project_id'},
                'overdue_tasks', order='date_deadline', date_fields=('date_deadline',), scope=scope,
            )
        missing_aa = []
        if self._has_field('project.project', 'account_id'):
            missing_aa = self._document_rows(
                'project.project', domain + [('active', '=', True), ('account_id', '=', False)],
                {'name': 'name'}, 'projects', order='name', scope=scope,
            )
        consumption_rows = []
        if self._can_read('ages.material.consumption'):
            consumption_rows = self._document_rows(
                'ages.material.consumption',
                self._scope_domain('ages.material.consumption', scope) + self._date_domain('date', date_from, date_to),
                {'name': 'name', 'date': 'date', 'project': 'project_id', 'state': 'state', 'amount': 'amount_total'},
                'material_consumption', order='date desc', money_fields=('amount_total',), date_fields=('date',), scope=scope,
            )
        open_po_rows = []
        if self._can_read('purchase.order'):
            open_po_rows = self._document_rows(
                'purchase.order',
                self._scope_domain('purchase.order', scope, [
                    ('state', 'in', ('purchase', 'done')),
                    ('invoice_status', 'in', ('no', 'to invoice')),
                ]),
                {'name': 'name', 'vendor': 'partner_id', 'amount': 'amount_untaxed'},
                'purchase_orders', order='date_order desc', money_fields=('amount_untaxed',), scope=scope,
            )
        payroll_rows = []
        if self._capability_map().get('payroll') and self._has_field('hr.payslip', 'project_id'):
            groups = self.env['hr.payslip'].read_group(
                self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))]) + self._date_domain('date_from', date_from, date_to),
                ['net_wage:sum'], ['project_id'], lazy=False,
            )
            for group in groups[:15]:
                project = group.get('project_id')
                payroll_rows.append({
                    'name': project[1] if project else 'Unassigned',
                    'net': self._format_money(group.get('net_wage') or 0.0, scope),
                    'res_id': project[0] if project else False,
                    'res_field': 'project_id',
                    'action_key': 'payslips',
                })
        project_income = self._aml_grouped(scope, income_extra, date_from, date_to, 'move_id.ages_project_id', invert=True)
        unassigned_rows = []
        if self._can_read('account.move.line'):
            unassigned_groups = self._aml_grouped(
                scope,
                expense_extra + [('analytic_distribution', '=', False)],
                date_from, date_to, 'move_id.ages_project_id',
            )
            unassigned_rows = [{
                'name': row.get('name') or 'Unassigned',
                'formatted': row.get('formatted'),
                'action_key': 'aml_expense',
            } for row in unassigned_groups]
        performance_rows = self._project_financial_rows(scope, project_income, self._analytic_project_rows(
            scope, expense_extra, date_from, date_to, limit=0
        ))
        tables = {
            'ranking': self._mgmt_table('Project recorded financial ranking', [
                {'key': 'name', 'label': 'Project'},
                {'key': 'income', 'label': 'Income'},
                {'key': 'cost', 'label': 'Cost'},
                {'key': 'margin', 'label': 'Recorded margin'},
            ], performance_rows, 'aml_income'),
            'unassigned_aml': self._mgmt_table('Projects with unassigned accounting amounts', [
                {'key': 'name', 'label': 'Project header'}, {'key': 'formatted', 'label': 'Expense without analytic'},
            ], unassigned_rows, 'aml_expense', empty='No posted expense AML with empty analytic_distribution.'),
            'overdue_tasks': self._mgmt_table('Overdue tasks', [
                {'key': 'name', 'label': 'Task'}, {'key': 'project', 'label': 'Project'}, {'key': 'deadline', 'label': 'Deadline'},
            ], overdue_task_rows, 'overdue_tasks'),
            'missing_aa': self._mgmt_table('Projects missing analytic account', [
                {'key': 'name', 'label': 'Project'},
            ], missing_aa, 'projects', empty='No projects missing account_id, or the field is absent.'),
            'open_po': self._mgmt_table('Projects with open procurement', [
                {'key': 'name', 'label': 'PO'}, {'key': 'vendor', 'label': 'Vendor'}, {'key': 'amount', 'label': 'Untaxed'},
            ], open_po_rows, 'purchase_orders'),
            'consumption': self._mgmt_table('Project material consumption', [
                {'key': 'name', 'label': 'Document'}, {'key': 'date', 'label': 'Date'},
                {'key': 'project', 'label': 'Project'}, {'key': 'state', 'label': 'State'}, {'key': 'amount', 'label': 'Amount'},
            ], consumption_rows, 'material_consumption'),
            'payroll': self._mgmt_table('Project payroll and attendance summary', [
                {'key': 'name', 'label': 'Project'}, {'key': 'net', 'label': 'Payroll net'},
            ], payroll_rows, 'payslips'),
        }
        warnings = []
        if coverage is not False:
            warnings.append('Analytic coverage %s%%. Margin is labelled recorded, not complete profit.' % coverage)
        warnings.append('Unassigned analytic income/cost uses posted AML with empty analytic_distribution.')
        self._attach_sparklines(kpis, {'revenue': (charts.get('pnl'), 0, 'money')})
        extra = {'layout': self._dashboard_layout(
            kind='standard',
            hero=['active', 'revenue', 'cost', 'margin', 'backlog', 'overdue_tasks'],
            charts=[('pnl', 8), ('tasks', 4), ('contract_projects', 12), ('backlog', 6), ('procurement', 6)],
            tables=['overdue_tasks', 'missing_aa', 'open_po', 'consumption'],
        )}
        if coverage is not False:
            extra['progress'] = {'label': 'Analytic coverage', 'value': coverage}
        return self._payload(
            scope, 'projects', kpis, charts, tables,
            date_field='account.move.line.date', warnings=warnings, extra=extra,
        )

    def _project_contract_positions(self, scope, limit=12):
        contract_rows = self._currency_grouped(
            'ages.contract', self._scope_domain('ages.contract', scope),
            'total_work_done_value', 'project_id', scope,
            date_field='date_start', company_currency=True, limit=0,
        ) if self._can_read('ages.contract') else []
        ra_rows = self._currency_grouped(
            'ages.running.bill',
            self._scope_domain('ages.running.bill', scope, [('state', '!=', 'cancelled')]),
            'value_of_work_done', 'project_id', scope,
            date_field='date', company_currency=True, limit=0,
        ) if self._can_read('ages.running.bill') else []
        project_ids = {
            row.get('res_id') for row in contract_rows + ra_rows if row.get('res_id')
        }
        rows = []
        for project_id in project_ids:
            contract = next((row['amount'] for row in contract_rows if row.get('res_id') == project_id), 0.0)
            ra = next((row['amount'] for row in ra_rows if row.get('res_id') == project_id), 0.0)
            source = next(
                (row for row in contract_rows + ra_rows if row.get('res_id') == project_id), {}
            )
            backlog = max(contract - ra, 0.0)
            rows.append({
                'name': source.get('name') or 'Unassigned',
                'contract_raw': round(contract, 2),
                'ra_raw': round(ra, 2),
                'backlog_raw': round(backlog, 2),
            })
        rows.sort(key=lambda row: row['contract_raw'], reverse=True)
        return rows[:limit]

    def _project_financial_rows(self, scope, income_rows, cost_rows):
        project_ids = {
            row.get('res_id') for row in list(income_rows or []) + list(cost_rows or [])
            if row.get('res_id')
        }
        rows = []
        for project_id in project_ids:
            income_row = next((row for row in income_rows if row.get('res_id') == project_id), {})
            cost_row = next((row for row in cost_rows if row.get('res_id') == project_id), {})
            income = income_row.get('amount') or 0.0
            cost = cost_row.get('amount') or 0.0
            analytic_id = (
                income_row.get('analytic_account_id')
                or cost_row.get('analytic_account_id')
            )
            rows.append({
                'name': income_row.get('name') or cost_row.get('name') or 'Project',
                'income': self._format_money(income, scope),
                'cost': self._format_money(cost, scope),
                'margin': self._format_money(income - cost, scope),
                'res_id': project_id,
                'res_value': [analytic_id] if analytic_id else False,
                'res_field': 'analytic_distribution',
                'res_operator': 'in',
                'action_key': 'aml_income' if analytic_id else 'projects',
                'margin_raw': income - cost,
            })
        rows.sort(key=lambda row: row['margin_raw'], reverse=True)
        return rows

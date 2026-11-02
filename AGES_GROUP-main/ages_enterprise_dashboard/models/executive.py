# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardExecutive(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_executive_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        date_from, date_to = scope['date_from'], scope['date_to']
        prev_from, prev_to = scope['previous_from'], scope['previous_to']
        income_extra = [('account_id.account_type', 'in', ('income', 'income_other'))]
        expense_extra = [('account_id.account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))]
        cash_extra = [('account_id.account_type', '=', 'asset_cash')]

        revenue = self._aml_sum(scope, income_extra, date_from, date_to, invert=True)
        expenses = self._aml_sum(scope, expense_extra, date_from, date_to)
        prev_revenue = self._aml_sum(scope, income_extra, prev_from, prev_to, invert=True)
        prev_expenses = self._aml_sum(scope, expense_extra, prev_from, prev_to)
        profit = revenue - expenses
        prev_profit = prev_revenue - prev_expenses
        cash = self._aml_sum(scope, cash_extra, None, date_to)

        ar_ap = self._snapshot_ar_ap(scope)
        receivables = ar_ap['receivables']
        payables = ar_ap['payables']
        aged_ar = ar_ap['aged_ar']
        aged_ap = ar_ap['aged_ap']

        ra_period = self._ra_sums(scope, [('state', '=', 'confirmed')], date_from, date_to)
        ra_amount = ra_period.get('net') or 0.0
        ra_work = ra_period.get('work') or 0.0
        ra_receivable = ra_period.get('receivable') or 0.0
        backlog = 0.0
        contract_value = 0.0
        billed = 0.0
        if self._can_read('ages.contract'):
            contract_domain = self._scope_domain('ages.contract', scope)
            if self._has_field('ages.contract', 'state'):
                contract_domain = contract_domain + [('state', '!=', 'cancelled')]
            contract_value = self._currency_sum(
                'ages.contract', contract_domain, 'total_work_done_value', scope,
                date_field='date_start', company_currency=True,
            )
        if self._can_read('ages.running.bill'):
            billed = self._ra_sums(scope, [('state', '!=', 'cancelled')]).get('work') or 0.0
            backlog = max((contract_value or 0.0) - (billed or 0.0), 0.0)

        po_open = po_unreceived = 0.0
        if self._can_read('purchase.order'):
            po_domain = self._scope_domain('purchase.order', scope, [
                ('state', 'in', ('purchase', 'done')),
                ('invoice_status', 'in', ('no', 'to invoice')),
            ])
            po_open = self._currency_sum(
                'purchase.order', po_domain, 'amount_untaxed', scope,
                date_field='date_order', company_currency=True,
            )
            if self._has_field('purchase.order', 'receipt_status'):
                po_unreceived = self._currency_sum(
                    'purchase.order',
                    self._scope_domain('purchase.order', scope, [
                        ('state', 'in', ('purchase', 'done')),
                        ('receipt_status', 'in', ('pending', 'partial')),
                    ]),
                    'amount_untaxed', scope, date_field='date_order', company_currency=True,
                )

        stock_value = 0.0
        if self._can_read('stock.valuation.layer'):
            stock_value = self._currency_sum(
                'stock.valuation.layer',
                self._scope_domain('stock.valuation.layer', scope),
                'value', scope, company_currency=True,
            )

        employees = 0
        if self._can_read('hr.employee'):
            employees = self._search_count('hr.employee', self._scope_domain('hr.employee', scope) + [('active', '=', True)])

        payroll_cost = 0.0
        if self._capability_map().get('payroll'):
            slip_domain = self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))])
            slip_domain += self._date_domain('date_from', date_from, date_to)
            payroll_cost = self._currency_sum(
                'hr.payslip', slip_domain, 'net_wage', scope,
                date_field='date_from', company_currency=True,
            )

        coverage = self._analytic_coverage(scope, date_from, date_to)
        warnings = []
        if coverage is not False and coverage < 100:
            warnings.append('Analytic coverage on posted journal items is %s%% in this period.' % coverage)

        bank_balance, cash_hand = self._cash_bank_snapshot(scope, date_to)
        collections = self._payment_sum(scope, 'inbound', date_from, date_to)
        vendor_payments = self._payment_sum(scope, 'outbound', date_from, date_to)
        sales_value = False
        if self._capability_map().get('sale') and self._can_read('sale.order'):
            sales_value = self._read_group_sum(
                'sale.order',
                self._scope_domain('sale.order', scope, [('state', 'in', ('sale', 'done'))]) + self._date_domain('date_order', date_from, date_to),
                'amount_untaxed',
            )
        active_projects = 0
        if self._can_read('project.project'):
            active_projects = self._search_count(
                'project.project',
                self._scope_domain('project.project', scope) + [('active', '=', True)],
            )
        att_hours = overtime = 0.0
        if self._can_read('hr.attendance'):
            att_domain = self._scope_domain('hr.attendance', scope) + self._datetime_date_domain('check_in', date_from, date_to)
            if self._has_field('hr.attendance', 'worked_hours'):
                att_hours = self._read_group_sum('hr.attendance', att_domain, 'worked_hours')
            if self._has_field('hr.attendance', 'validated_overtime_hours'):
                overtime = self._read_group_sum('hr.attendance', att_domain, 'validated_overtime_hours')
        negative_stock = 0
        if self._can_read('stock.quant'):
            negative_stock = self._search_count(
                'stock.quant',
                self._scope_domain('stock.quant', scope) + [('quantity', '<', 0), ('location_id.usage', '=', 'internal')],
            )
        reorder_data = self._below_reorder_data(scope) if self._can_read('stock.warehouse.orderpoint') else {'available': False, 'count': 0}
        gate_wait = 0
        if self._can_read('ages.gate.pass') and self._has_field('ages.gate.pass', 'state'):
            waiting = ['draft']
            try:
                selection = self.env['ages.gate.pass']._fields['state'].selection
                if callable(selection):
                    selection = selection(self.env['ages.gate.pass'])
                if 'waiting_security' in dict(selection or []):
                    waiting.append('waiting_security')
            except Exception:
                pass
            gate_wait = self._search_count(
                'ages.gate.pass',
                self._scope_domain('ages.gate.pass', scope, [('state', 'in', tuple(waiting))]),
            )

        kpis = [
            self._kpi(scope, 'revenue', 'Revenue', revenue, prev_revenue, 'aml_income',
                      'Posted AML income accounts; displayed as positive income.'),
            self._kpi(scope, 'expenses', 'Accounting expenses', expenses, prev_expenses, 'aml_expense',
                      'Posted AML expense account types.'),
            self._kpi(scope, 'profit', 'Net result', profit, prev_profit, False,
                      'Revenue minus accounting expenses on the same posted-AML basis.'),
            self._kpi(scope, 'cash', 'Cash & bank', cash, False, 'aml_cash_snapshot',
                      'Posted cash/bank AML balance through the end date (snapshot).'),
            self._kpi(scope, 'bank', 'Bank', bank_balance, False, 'aml_bank_snapshot',
                      'Posted asset_cash AML on bank journals through date_to (snapshot).',
                      basis='snapshot'),
            self._kpi(scope, 'cash_in_hand', 'Cash in hand', cash_hand, False, 'aml_cash_hand_snapshot',
                      'Posted asset_cash AML on cash journals through date_to (snapshot).',
                      basis='snapshot'),
            self._kpi(scope, 'receivables', 'Receivables', receivables, ar_ap['previous_receivables'], 'customer_receivables',
                      'As-of AgedPartnerBalanceEngine total at date_to.' if ar_ap['ar_basis'] == 'aged_engine' else 'Live posted customer invoice residual. Aging engine was not available.'),
            self._kpi(scope, 'payables', 'Payables', payables, ar_ap['previous_payables'], 'vendor_payables',
                      'As-of AgedPartnerBalanceEngine total at date_to. Retention remains on its GL.' if ar_ap['ap_basis'] == 'aged_engine' else 'Live posted vendor residual. Retention payable lines remain on their GL.'),
            self._kpi(scope, 'collections', 'Collections', collections, False, 'customer_collections',
                      'Inbound paid/in-process payments excluding internal transfers.'),
            self._kpi(scope, 'vendor_payments', 'Vendor payments', vendor_payments, False, 'vendor_payments',
                      'Outbound paid/in-process payments excluding internal transfers.'),
            self._kpi(scope, 'ra_work', 'RA work this period', ra_work, False, 'running_bills',
                      'Confirmed value_of_work_done (A) in the selected period. Current-bill amount, not cumulative.'),
            self._kpi(scope, 'ra_receivable', 'RA receivable this period', ra_receivable, False, 'running_bills',
                      'Confirmed total_receivable including sales tax in the selected period.'),
            self._kpi(scope, 'ra_billed', 'RA billed (net)', ra_amount, False, 'running_bills',
                      'Confirmed running bills net_amount in the selected period.'),
            self._kpi(scope, 'backlog', 'Unbilled contract work', backlog, False, 'contracts',
                      'Contract work value minus non-cancelled RA work. Not accounting revenue.'),
            self._kpi(scope, 'po_open', 'PO not yet billed', po_open, False, 'purchase_commitments',
                      'Confirmed POs whose invoice_status is no/to invoice, untaxed amount.'),
            self._kpi(scope, 'po_unreceived', 'PO not yet received', po_unreceived, False, 'pending_po_receipts',
                      'Confirmed POs whose receipt_status is pending or partial.') if self._has_field('purchase.order', 'receipt_status') else self._unavailable_kpi(scope, 'po_unreceived', 'PO not yet received', 'purchase.order.receipt_status is not present.'),
            self._kpi(scope, 'stock', 'Inventory value', stock_value, False, 'stock_valuation',
                      'Live remaining stock.valuation.layer.value (snapshot). Not historical as-of stock.',
                      basis='snapshot', limitations='SVL remaining value only; no reconstructed as-of inventory.'),
            self._kpi(scope, 'employees', 'Active employees', employees, False, 'active_employees',
                      'Active employee records in scope.', suffix=''),
            self._kpi(scope, 'projects', 'Active projects', active_projects, False, 'projects',
                      'Active project.project records in scope.', suffix='', basis='count'),
            self._kpi(scope, 'att_hours', 'Attendance hours', att_hours, False, 'attendances',
                      'SUM(hr.attendance.worked_hours) in the period.', suffix='', basis='count') if self._can_read('hr.attendance') else self._unavailable_kpi(scope, 'att_hours', 'Attendance hours', 'hr.attendance is not readable.'),
            self._kpi(scope, 'overtime', 'Validated overtime', overtime, False, 'attendances',
                      'SUM(validated_overtime_hours) on attendance in the period.', suffix='', basis='count') if self._has_field('hr.attendance', 'validated_overtime_hours') else self._unavailable_kpi(scope, 'overtime', 'Overtime hours', 'validated_overtime_hours is not present on hr.attendance.'),
            self._kpi(scope, 'negative_stock', 'Negative stock', negative_stock, False, 'negative_stock',
                      'Internal quants with quantity < 0.', suffix='', basis='count'),
            self._kpi(scope, 'low_stock', 'Below-reorder products', reorder_data.get('count') or 0, False, 'below_reorder',
                      'Standard orderpoint qty_on_hand compared with stored product_min_qty.', suffix='', basis='count') if reorder_data.get('available') else self._unavailable_kpi(scope, 'low_stock', 'Below-reorder products', reorder_data.get('reason') or 'Reordering rules are not readable.'),
            self._kpi(scope, 'gate_wait', 'Gate-pass exceptions', gate_wait, False, 'waiting_gate_passes',
                      'Gate passes still in draft or waiting security.', suffix='', basis='count') if self._can_read('ages.gate.pass') else self._unavailable_kpi(scope, 'gate_wait', 'Gate-pass exceptions', 'ages.gate.pass is not readable.'),
        ]
        if sales_value is not False:
            kpis.insert(14, self._kpi(
                scope, 'sales', 'Confirmed sales', sales_value, False, 'sale_orders',
                'Confirmed sale.order amount_untaxed in the selected date_order range.',
            ))
        if self._capability_map().get('payroll'):
            kpis.append(self._kpi(scope, 'payroll', 'Payroll net', payroll_cost, False, 'payslips',
                                  'Finalized/paid payslip net wage. Hidden unless payroll access is granted.'))

        labels, revenue_trend = self._monthly_aml_trend(scope, income_extra, invert=True)
        _labels, expense_trend = self._monthly_aml_trend(scope, expense_extra)
        profit_trend = [round(rev - exp, 2) for rev, exp in zip(revenue_trend, expense_trend)]
        cash_labels, cash_datasets = self._cash_flow_trend(scope)
        project_income = self._analytic_project_rows(scope, income_extra, date_from, date_to, invert=True, limit=8)
        project_cost = self._analytic_project_rows(scope, expense_extra, date_from, date_to, limit=8)
        project_ids = list({row.get('res_id') for row in (project_income + project_cost) if row.get('res_id')})
        project_names = {row.get('res_id'): row.get('name') for row in (project_income + project_cost)}
        charts = {
            'pnl': self._chart('mixed', 'Revenue vs expenses vs result', labels, [
                {'label': 'Revenue', 'data': revenue_trend, 'type': 'bar'},
                {'label': 'Expenses', 'data': expense_trend, 'type': 'bar'},
                {'label': 'Result', 'data': profit_trend, 'type': 'line'},
            ], unit='money', size='lg', subtitle='Posted AML · %s' % (self._currency(scope).name or ''),
               allow_toggle=True, why_key='revenue'),
            'cash_comp': self._chart(
                'doughnut', 'Cash composition', ['Bank', 'Cash in hand'],
                [{'label': 'Balance', 'data': [round(bank_balance or 0.0, 2), round(cash_hand or 0.0, 2)]}],
                unit='money', size='sm', variant='doughnut',
                center_label=self._format_money(cash or 0.0, scope),
                subtitle='Snapshot through %s' % (date_to or ''),
            ),
            'cash': self._chart(
                'stackedBar', 'Cash movement', cash_labels, cash_datasets,
                unit='money', size='md', allow_toggle=True,
            ),
            'backlog': self._chart(
                'horizontalBar', 'RA work vs unpaid vs backlog',
                ['RA work this period', 'Unpaid RA receivable', 'Backlog'],
                [{'label': 'Amount', 'data': [
                    round(ra_work or 0.0, 2),
                    round(ra_receivable or 0.0, 2),
                    round(backlog, 2),
                ]}],
                unit='money', size='md',
            ),
            'projects': self._chart(
                'horizontalBar', 'Project recorded financial position',
                [project_names.get(res_id) or 'Unassigned' for res_id in project_ids],
                [
                    {'label': 'Income', 'data': [
                        next((row['amount'] for row in project_income if row.get('res_id') == res_id), 0.0)
                        for res_id in project_ids
                    ]},
                    {'label': 'Cost', 'data': [
                        next((row['amount'] for row in project_cost if row.get('res_id') == res_id), 0.0)
                        for res_id in project_ids
                    ]},
                ],
                action_key='projects', group_field='id', label_ids=project_ids,
                unit='money', size='md',
            ),
        }
        if self._can_read('hr.employee') and self._has_field('hr.employee', 'department_id'):
            charts['workforce_dept'] = self._group_chart(
                'hr.employee', self._scope_domain('hr.employee', scope) + [('active', '=', True)],
                'department_id', 'Workforce by department',
            )
        if self._can_read('hr.employee') and self._has_field('hr.employee', 'project_id'):
            charts['workforce_project'] = self._group_chart(
                'hr.employee', self._scope_domain('hr.employee', scope) + [('active', '=', True)],
                'project_id', 'Workforce by project',
            )

        tables = {
            'overdue_customers': self._overdue_partner_table(scope, 'out_invoice', 'Top overdue customers', 'overdue_invoices'),
            'overdue_vendors': self._overdue_partner_table(scope, 'in_invoice', 'Top vendor obligations', 'overdue_bills'),
            'projects': self._project_attention_table(scope),
            'expiring': self._expiring_contracts_table(scope),
            'overrun': self._contract_overrun_table(scope),
            'approvals': self._pending_approvals_table(scope),
            'low_stock': self._low_stock_table(scope),
        }
        if aged_ar:
            warnings.append('Receivable aging uses AgedPartnerBalanceEngine as-of %s.' % aged_ar.get('date_label'))
        revenue_runrate = self._run_rate_projection(revenue, date_from, date_to)
        if revenue_runrate is not False:
            kpis.append(self._kpi(
                scope, 'revenue_runrate', 'Revenue run-rate projection', revenue_runrate, False, 'aml_income',
                'Linear run-rate from elapsed days in the selected period to period end. Not a committed forecast.',
                basis='forecast',
            ))
        main_summary = self._main_summary_payload(scope)
        if main_summary and main_summary.get('kpis'):
            ms = main_summary['kpis']
            tables['main_summary'] = self._mgmt_table('Main Summary cash engine', [
                {'key': 'name', 'label': 'Bucket'}, {'key': 'amount', 'label': 'Amount'},
            ], [
                {'name': 'Opening', 'amount': self._format_money(ms.get('opening') or 0.0, scope)},
                {'name': 'Received', 'amount': self._format_money(ms.get('received') or 0.0, scope)},
                {'name': 'Cash out', 'amount': self._format_money(ms.get('expenses') or 0.0, scope)},
                {'name': 'Closing', 'amount': self._format_money(ms.get('closing') or 0.0, scope)},
            ], 'aml_cash')
        skip_attention = {'deletion_audit'}
        attention = [
            queue for queue in self._action_center_queues(scope)
            if queue.get('count') and queue.get('key') not in skip_attention
        ][:4]
        self._attach_sparklines(kpis, {
            'revenue': (charts.get('pnl'), 0, 'money'),
            'expenses': (charts.get('pnl'), 1, 'money'),
            'profit': (charts.get('pnl'), 2, 'money'),
            'cash': (charts.get('cash'), 2, 'money'),
            'ra_work': (charts.get('backlog'), 0, 'money'),
        })
        return self._payload(
            scope, 'executive', kpis, charts, tables, alerts=attention,
            date_field='account.move.line.date', warnings=warnings,
            extra={
                'layout': self._dashboard_layout(
                    kind='executive',
                    hero=['revenue', 'profit', 'cash', 'receivables', 'ra_work'],
                    alerts=[queue['key'] for queue in attention],
                    alert_title='Priority workbench · Cash & credit',
                    charts=[('pnl', 8), ('cash_comp', 4), ('cash', 6), ('backlog', 6)],
                    tables=['overdue_customers', 'expiring'],
                    more=[
                        'bank', 'cash_in_hand', 'payables', 'collections', 'vendor_payments',
                        'po_open', 'stock', 'employees', 'projects', 'att_hours',
                        'negative_stock', 'gate_wait', 'payroll', 'revenue_runrate',
                    ],
                ),
            },
        )

    def _cash_flow_trend(self, scope, months=6):
        extra = [('account_id.account_type', '=', 'asset_cash')]
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        labels = []
        inflow = []
        outflow = []
        net = []
        from datetime import timedelta
        cursor = date_to.replace(day=1)
        buckets = []
        for _index in range(months):
            buckets.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        buckets.reverse()
        for month_start in buckets:
            month_end = fields.Date.end_of(month_start, 'month')
            if month_end > date_to:
                month_end = date_to
            labels.append(month_start.strftime('%b %Y'))
            debit_domain = self._aml_posted_domain(scope, extra + [('debit', '>', 0)]) + self._date_domain('date', month_start, month_end)
            credit_domain = self._aml_posted_domain(scope, extra + [('credit', '>', 0)]) + self._date_domain('date', month_start, month_end)
            inn = self._read_group_sum('account.move.line', debit_domain, 'debit')
            out = self._read_group_sum('account.move.line', credit_domain, 'credit')
            inflow.append(round(inn or 0.0, 2))
            outflow.append(round(out or 0.0, 2))
            net.append(round((inn or 0.0) - (out or 0.0), 2))
        return labels, [
            {'label': 'Inflow', 'data': inflow},
            {'label': 'Outflow', 'data': outflow},
            {'label': 'Net', 'data': net, 'type': 'line'},
        ]

    def _overdue_partner_table(self, scope, move_type, title, action_key):
        if not self._can_read('account.move'):
            return self._mgmt_table(title, [], [], action_key)
        today = fields.Date.context_today(self)
        domain = self._scope_domain('account.move', scope, [
            ('move_type', '=', move_type),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', today),
        ])
        rows = self._currency_grouped(
            'account.move', domain, 'amount_residual_signed', 'partner_id', scope,
            date_field='date', company_currency=True, limit=10,
        )
        table_rows = []
        for group in rows:
            residual = group.get('amount') or 0.0
            table_rows.append({
                'name': group.get('name') or 'Unknown',
                'residual': self._format_money(residual, scope),
                'residual_raw': residual,
                'res_id': group.get('res_id'),
                'res_field': 'partner_id',
                'action_key': action_key,
            })
        return self._mgmt_table(title, [
            {'key': 'name', 'label': 'Partner'},
            {'key': 'residual', 'label': 'Residual'},
        ], table_rows, action_key)

    def _project_attention_table(self, scope):
        if not self._can_read('project.project'):
            return self._mgmt_table('Projects needing attention', [], [])
        project_domain = self._scope_domain('project.project', scope) + [('active', '=', True)]
        attention = {}
        today = fields.Date.context_today(self)
        if self._has_field('project.project', 'date'):
            for project in self._search_read(
                'project.project', project_domain + [('date', '<', today)],
                ['name', 'date'], limit=0, order='date',
            ):
                attention.setdefault(project['id'], set()).add('Project deadline passed')
        if self._has_field('project.project', 'account_id'):
            for project in self._search_read(
                'project.project', project_domain + [('account_id', '=', False)],
                ['name', 'date'], limit=0, order='name',
            ):
                attention.setdefault(project['id'], set()).add('Missing analytic account')
        if self._can_read('project.task') and self._has_field('project.task', 'date_deadline'):
            groups = self.env['project.task'].read_group(
                self._scope_domain('project.task', scope, [
                    ('date_deadline', '<', today),
                    ('state', 'not in', ('1_done', '1_canceled')),
                ]),
                ['id:count'], ['project_id'], lazy=False,
            )
            for group in groups:
                project = group.get('project_id')
                if project:
                    count = group.get('project_id_count') or group.get('__count') or 0
                    attention.setdefault(project[0], set()).add('%s overdue task(s)' % count)
        projects = self._search_read(
            'project.project', project_domain + [('id', 'in', list(attention) or [0])],
            ['name', 'date'], limit=12, order='date, name',
        )
        rows = []
        for project in projects:
            rows.append({
                'name': project.get('name'),
                'date': self._format_date(project.get('date')),
                'reason': '; '.join(sorted(attention.get(project['id'], set()))),
                'res_id': project.get('id'),
                'action_key': 'projects',
            })
        return self._mgmt_table('Projects requiring attention', [
            {'key': 'name', 'label': 'Project'},
            {'key': 'date', 'label': 'Deadline'},
            {'key': 'reason', 'label': 'Reason'},
        ], rows, 'projects')

    def _purchase_qty_snapshot(self, scope):
        if not self._can_read('purchase.order.line'):
            return [0.0, 0.0, 0.0]
        domain = self._scope_domain('purchase.order.line', scope)
        ordered = self._read_group_sum('purchase.order.line', domain, 'product_qty') or 0.0
        received = self._read_group_sum('purchase.order.line', domain, 'qty_received') if self._has_field('purchase.order.line', 'qty_received') else 0.0
        invoiced = self._read_group_sum('purchase.order.line', domain, 'qty_invoiced') if self._has_field('purchase.order.line', 'qty_invoiced') else 0.0
        return [round(ordered, 2), round(received or 0.0, 2), round(invoiced or 0.0, 2)]

    def _purchase_qty_monthly(self, scope, months=6):
        if not self._can_read('purchase.order.line') or not self._field_path_exists('purchase.order.line', 'date_order'):
            return [], [], [], []
        buckets, date_to = self._month_starts(scope, months)
        labels, ordered, received, billed = [], [], [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            domain = self._scope_domain('purchase.order.line', scope) + self._date_domain('date_order', month_start, month_end)
            ordered.append(round(self._read_group_sum('purchase.order.line', domain, 'product_qty') or 0.0, 2))
            received.append(round(self._read_group_sum('purchase.order.line', domain, 'qty_received') or 0.0, 2) if self._has_field('purchase.order.line', 'qty_received') else 0.0)
            billed.append(round(self._read_group_sum('purchase.order.line', domain, 'qty_invoiced') or 0.0, 2) if self._has_field('purchase.order.line', 'qty_invoiced') else 0.0)
        return labels, ordered, received, billed

    def _expiring_contracts_table(self, scope):
        if not self._can_read('ages.contract') or not self._has_field('ages.contract', 'date_close'):
            return self._mgmt_table('Contracts nearing close', [], [], 'contracts')
        expiry_days = self._config_int('ages_enterprise_dashboard.contract_expiry_days', 30)
        close_horizon = (scope.get('date_to') or fields.Date.context_today(self)) + timedelta(days=expiry_days)
        records = self._search_read(
            'ages.contract',
            self._scope_domain('ages.contract', scope) + [
                ('state', 'in', ('new', 'running')),
                ('date_close', '!=', False),
                ('date_close', '<=', close_horizon),
            ],
            ['name', 'date_close', 'partner_id', 'total_work_done_value'],
            limit=12, order='date_close',
        )
        rows = []
        for rec in records:
            partner = rec.get('partner_id')
            rows.append({
                'name': rec.get('name'),
                'date_close': self._format_date(rec.get('date_close')),
                'partner': partner[1] if partner else '',
                'value': self._format_money(rec.get('total_work_done_value') or 0.0, scope),
                'res_id': rec.get('id'),
                'action_key': 'expiring_contracts',
            })
        return self._mgmt_table('Contracts nearing close', [
            {'key': 'name', 'label': 'Contract'},
            {'key': 'partner', 'label': 'Client'},
            {'key': 'date_close', 'label': 'Close date'},
            {'key': 'value', 'label': 'Value'},
        ], rows, 'expiring_contracts')

    def _contract_overrun_table(self, scope):
        if not self._can_read('ages.contract') or not self._can_read('ages.running.bill'):
            return self._mgmt_table('Contracts billed above value', [], [], 'contracts')
        _performance, overrun = self._contract_performance(scope)
        return self._mgmt_table('Contracts billed above contract value', [
            {'key': 'name', 'label': 'Contract'},
            {'key': 'partner', 'label': 'Client'},
            {'key': 'value', 'label': 'Contract value'},
            {'key': 'billed', 'label': 'RA work'},
        ], overrun, 'contracts')

    def _pending_approvals_table(self, scope):
        rows = []
        if self._has_field('account.payment', 'validation_status'):
            amount_field = (
                'amount_company_currency_signed'
                if self._has_field('account.payment', 'amount_company_currency_signed')
                else 'amount'
            )
            records = self._search_read(
                'account.payment',
                self._scope_domain('account.payment', scope, [
                    ('validation_status', 'in', ('waiting', 'pending')),
                ]),
                ['name', 'date', amount_field], limit=10, order='%s desc' % amount_field,
            )
            for record in records:
                amount = abs(record.get(amount_field) or 0.0)
                rows.append({
                    'name': record.get('name'),
                    'queue': 'Payment',
                    'amount': self._format_money(amount, scope),
                    'amount_raw': amount,
                    'res_id': record.get('id'),
                    'action_key': 'pending_payments',
                })
        if self._has_field('purchase.request', 'validation_status'):
            records = self._search_read(
                'purchase.request',
                self._scope_domain('purchase.request', scope, [
                    ('validation_status', 'in', ('waiting', 'pending')),
                ]),
                ['name', 'date_start', 'estimated_cost'], limit=10, order='estimated_cost desc',
            )
            for record in records:
                amount = record.get('estimated_cost') or 0.0
                rows.append({
                    'name': record.get('name'),
                    'queue': 'Purchase request',
                    'amount': self._format_money(amount, scope),
                    'amount_raw': amount,
                    'res_id': record.get('id'),
                    'action_key': 'pending_pr',
                })
        if self._has_field('account.move', 'je_stage'):
            records = self._search_read(
                'account.move',
                self._scope_domain('account.move', scope, [('je_stage', '=', 'validate')]),
                ['name', 'date', 'amount_total_signed'], limit=10, order='amount_total_signed desc',
            )
            for record in records:
                amount = abs(record.get('amount_total_signed') or 0.0)
                rows.append({
                    'name': record.get('name'),
                    'queue': 'Journal entry',
                    'amount': self._format_money(amount, scope),
                    'amount_raw': amount,
                    'res_id': record.get('id'),
                    'action_key': 'je_validate',
                })
        rows.sort(key=lambda row: row.get('amount_raw') or 0.0, reverse=True)
        return self._mgmt_table('Largest pending approvals', [
            {'key': 'name', 'label': 'Document'},
            {'key': 'queue', 'label': 'Queue'},
            {'key': 'amount', 'label': 'Amount'},
        ], rows[:15])

    def _low_stock_table(self, scope):
        if self._can_read('stock.warehouse.orderpoint') and self._can_read('stock.quant'):
            data = self._below_reorder_data(scope)
            if data.get('available'):
                return self._below_reorder_table(scope, data)
        if not self._can_read('stock.quant'):
            return self._mgmt_table('Negative stock', [], [], 'negative_stock')
        records = self._search_read(
            'stock.quant',
            self._scope_domain('stock.quant', scope) + [('quantity', '<', 0), ('location_id.usage', '=', 'internal')],
            ['product_id', 'location_id', 'quantity'],
            limit=12, order='quantity',
        )
        rows = []
        for rec in records:
            product = rec.get('product_id')
            location = rec.get('location_id')
            rows.append({
                'product': product[1] if product else '',
                'location': location[1] if location else '',
                'qty': rec.get('quantity'),
                'res_id': rec.get('id'),
                'action_key': 'negative_stock',
            })
        return self._mgmt_table('Negative stock', [
            {'key': 'product', 'label': 'Product'},
            {'key': 'location', 'label': 'Location'},
            {'key': 'qty', 'label': 'Qty'},
        ], rows, 'negative_stock')

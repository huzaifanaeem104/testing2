# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardContracts(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_contracts_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._can_read('ages.contract'):
            return self._unavailable(scope, 'contracts', 'Contract records are not available or not readable.')
        date_from, date_to = scope['date_from'], scope['date_to']
        contract_domain = self._scope_domain('ages.contract', scope)
        total = self._search_count('ages.contract', contract_domain)
        running = self._search_count('ages.contract', contract_domain + [('state', '=', 'running')])
        closed = self._search_count('ages.contract', contract_domain + [('state', '=', 'closed')])
        new = self._search_count('ages.contract', contract_domain + [('state', '=', 'new')])
        contract_value = self._currency_sum(
            'ages.contract', contract_domain, 'total_work_done_value', scope,
            date_field='date_start', company_currency=True,
        )

        ra_period = self._ra_sums(scope, [('state', '=', 'confirmed')], date_from, date_to)
        ra_amount = ra_period.get('net') or 0.0
        ra_receivable = ra_period.get('receivable') or 0.0
        ra_receivable_ex = ra_period.get('receivable_ex') or 0.0
        ra_work = ra_period.get('work') or 0.0
        billed_work = self._ra_sums(scope, [('state', '!=', 'cancelled')]).get('work') or 0.0
        sales_tax = ra_period.get('sales_tax') or 0.0
        wth_amount = ra_period.get('wth') or 0.0
        material_recovery = ra_period.get('material') or 0.0
        retention_held = self._ra_sums(scope, [('state', '=', 'confirmed')]).get('retention') or 0.0
        mob_recovered = self._ra_sums(scope, [('state', '=', 'confirmed')]).get('mobilization') or 0.0
        paid = partial = unpaid = missing_invoice = 0
        wth_on_st = 0.0
        if self._can_read('ages.running.bill'):
            confirmed = self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')])
            if self._has_field('ages.running.bill', 'wth_on_sales_tax_amount'):
                wth_on_st = self._currency_sum(
                    'ages.running.bill', confirmed + self._date_domain('date', date_from, date_to),
                    'wth_on_sales_tax_amount', scope,
                    date_field='date', company_currency=True,
                )
            if self._has_field('ages.running.bill', 'invoice_payment_state'):
                paid = self._search_count('ages.running.bill', confirmed + [('invoice_payment_state', '=', 'paid')])
                partial = self._search_count('ages.running.bill', confirmed + [('invoice_payment_state', '=', 'partial')])
                unpaid = self._search_count('ages.running.bill', confirmed + [
                    ('invoice_payment_state', 'in', ('not_paid', 'in_payment')),
                ])
            if self._has_field('ages.running.bill', 'invoice_id'):
                missing_invoice = self._search_count('ages.running.bill', confirmed + [('invoice_id', '=', False)])

        backlog = max((contract_value or 0.0) - (billed_work or 0.0), 0.0)
        mob_received = 0.0
        if self._can_read('ages.mobilization.advance'):
            mob_received = self._currency_sum(
                'ages.mobilization.advance',
                self._scope_domain('ages.mobilization.advance', scope, [('state', '=', 'confirmed')]),
                'mobilization_amount',
                scope,
                date_field='date',
                company_currency=True,
            )
        retention_total = 0.0
        if self._has_field('ages.contract', 'total_retention_amount'):
            retention_total = self._currency_sum(
                'ages.contract', contract_domain, 'total_retention_amount', scope,
                date_field='date_start', company_currency=True,
            )
        retention_released = 0.0
        if self._can_read('ages.retention.recovery'):
            retention_released = self._currency_sum(
                'ages.retention.recovery',
                self._scope_domain('ages.retention.recovery', scope, [('state', '=', 'confirmed')]),
                'retention_amount',
                scope,
                date_field='date',
                company_currency=True,
            )
        mob_outstanding = max((mob_received or 0.0) - (mob_recovered or 0.0), 0.0)
        retention_outstanding = max((retention_held or 0.0) - (retention_released or 0.0), 0.0)

        expiry_days = self._config_int('ages_enterprise_dashboard.contract_expiry_days', 30)
        close_horizon = (scope['date_to'] or fields.Date.context_today(self)) + timedelta(days=expiry_days)
        expiring = []
        if self._has_field('ages.contract', 'date_close'):
            expiring = self._search_read(
                'ages.contract',
                contract_domain + [
                    ('state', 'in', ('new', 'running')),
                    ('date_close', '!=', False),
                    ('date_close', '<=', close_horizon),
                ],
                ['name', 'date_close', 'partner_id', 'total_work_done_value'],
                limit=15,
                order='date_close',
            )

        kpis = [
            self._kpi(scope, 'contracts', 'Contracts', total, False, 'contracts',
                      'Contract records in scope.', suffix='', basis='count', formula='COUNT ages.contract.'),
            self._kpi(scope, 'running', 'Running', running, False, 'contracts',
                      'Contracts in state running.', suffix='', basis='count', formula="COUNT state='running'."),
            self._kpi(scope, 'new', 'New', new, False, 'contracts',
                      'Contracts in state new.', suffix='', basis='count', formula="COUNT state='new'."),
            self._kpi(scope, 'closed', 'Closed', closed, False, 'contracts',
                      'Contracts in state closed.', suffix='', basis='count', formula="COUNT state='closed'."),
            self._kpi(scope, 'value', 'Contract work value', contract_value, False, 'contracts',
                      'Stored contract total_work_done_value (integer in current schema).',
                      basis='snapshot', formula='SUM(total_work_done_value).'),
            self._kpi(scope, 'ra_period', 'RA net this period', ra_amount, False, 'running_bills',
                      'Confirmed running-bill net_amount in the selected dates.',
                      basis='flow', date_field='ages.running.bill.date',
                      formula="SUM(net_amount) where state='confirmed'."),
            self._kpi(scope, 'ra_receivable', 'RA receivable this period', ra_receivable, False, 'running_bills',
                      'Confirmed total_receivable including sales tax.',
                      basis='flow', date_field='ages.running.bill.date',
                      formula='SUM(total_receivable) confirmed in period.'),
            self._kpi(scope, 'ra_receivable_ex', 'RA receivable ex sales tax', ra_receivable_ex, False, 'running_bills',
                      'Confirmed total_receivable_ex_sales_tax (gross receivable excluding sales tax).',
                      basis='flow', date_field='ages.running.bill.date',
                      formula='SUM(total_receivable_ex_sales_tax) confirmed in period.'),
            self._kpi(scope, 'ra_work', 'RA work this period', ra_work, False, 'running_bills',
                      'Current-bill value_of_work_done, not cumulative.',
                      basis='flow', date_field='ages.running.bill.date',
                      formula='SUM(value_of_work_done) confirmed in period.'),
            self._kpi(scope, 'billed', 'Cumulative RA work', billed_work, False, 'running_bills',
                      'Non-cancelled RA value_of_work_done across all dates.',
                      basis='snapshot', formula="SUM(value_of_work_done) where state != 'cancelled'."),
            self._kpi(scope, 'backlog', 'Unbilled contract work', backlog, False, 'contracts',
                      'Contract work value minus non-cancelled RA work. Not accounting revenue.',
                      basis='snapshot', formula='contract value − cumulative RA work.'),
            self._kpi(scope, 'paid_ra', 'RA invoices paid', paid, False, 'running_bills',
                      'Confirmed RA whose related invoice payment_state is paid.',
                      suffix='', basis='count', formula="COUNT invoice_payment_state='paid'."),
            self._kpi(scope, 'partial_ra', 'RA invoices partial', partial, False, 'unpaid_ra',
                      'Confirmed RA whose related invoice payment_state is partial.',
                      suffix='', basis='count', formula="COUNT invoice_payment_state='partial'."),
            self._kpi(scope, 'unpaid_ra', 'RA invoices unpaid', unpaid, False, 'unpaid_ra',
                      'Confirmed RA whose related invoice is not_paid or in_payment.',
                      suffix='', basis='count', formula="COUNT invoice_payment_state in not_paid/in_payment."),
            self._kpi(scope, 'missing_invoice', 'RA missing invoice', missing_invoice, False, 'missing_ra_invoices',
                      'Confirmed RA with invoice_id empty.',
                      suffix='', basis='count', formula='COUNT confirmed RA where invoice_id is empty.'),
            self._kpi(scope, 'material', 'Material recovery this period', material_recovery, False, 'running_bills',
                      'Confirmed RA material_recovery in the selected dates.',
                      basis='flow', date_field='ages.running.bill.date', formula='SUM(material_recovery).'),
            self._kpi(scope, 'sales_tax', 'RA sales tax this period', sales_tax, False, 'running_bills',
                      'Confirmed RA sales_tax_amount in the selected dates.',
                      basis='flow', date_field='ages.running.bill.date', formula='SUM(sales_tax_amount).'),
            self._kpi(scope, 'wth', 'RA withholding this period', wth_amount, False, 'running_bills',
                      'Confirmed RA wth_amount in the selected dates.',
                      basis='flow', date_field='ages.running.bill.date', formula='SUM(wth_amount).'),
            self._kpi(scope, 'wth_st', 'WHT on sales tax this period', wth_on_st, False, 'running_bills',
                      'Confirmed RA wth_on_sales_tax_amount in the selected dates.',
                      basis='flow', date_field='ages.running.bill.date', formula='SUM(wth_on_sales_tax_amount).'),
            self._kpi(scope, 'mob_received', 'Mobilization received', mob_received, False, 'mobilization',
                      'Confirmed ages.mobilization.advance mobilization_amount.',
                      basis='snapshot', formula="SUM(mobilization_amount) state='confirmed'."),
            self._kpi(scope, 'mob_recovered', 'Mobilization recovered on RA', mob_recovered, False, 'running_bills',
                      'Confirmed RA mobilization_amount (H).',
                      basis='snapshot', formula='SUM(ages.running.bill.mobilization_amount) confirmed.'),
            self._kpi(scope, 'mob_out', 'Mobilization outstanding', mob_outstanding, False, 'mobilization',
                      'Confirmed mobilization received minus RA recovery. Not a cash-engine figure.',
                      basis='snapshot', formula='received − recovered, floored at zero.'),
            self._kpi(scope, 'retention_held', 'Retention withheld on RA', retention_held, False, 'running_bills',
                      'Confirmed RA retention_amount (I).',
                      basis='snapshot', formula='SUM(retention_amount) confirmed RA.'),
            self._kpi(scope, 'retention_released', 'Retention released', retention_released, False, 'retention',
                      'Confirmed ages.retention.recovery retention_amount.',
                      basis='snapshot', formula="SUM(retention_amount) state='confirmed'."),
            self._kpi(scope, 'retention_out', 'Retention outstanding', retention_outstanding, False, 'retention',
                      'RA withheld minus confirmed retention recovery.',
                      basis='snapshot', formula='withheld − released, floored at zero.'),
            self._kpi(scope, 'retention_cap', 'Contract retention cap', retention_total, False, 'contracts',
                      'Stored contract total_retention_amount.',
                      basis='snapshot', formula='SUM(total_retention_amount).'),
        ]

        state_rows = self.env['ages.contract'].read_group(contract_domain, ['id:count'], ['state'], lazy=False)
        state_labels = [row.get('state') or 'unknown' for row in state_rows]
        state_data = [row.get('state_count') or row.get('id_count') or 0 for row in state_rows]
        monthly = self._ra_monthly(scope)
        pay_labels, pay_data = self._ra_payment_distribution(scope)
        clients = self._top_clients(scope)
        performance, overrun = self._contract_performance(scope)

        charts = {
            'states': self._chart('doughnut', 'Contract lifecycle', state_labels, [{'label': 'Contracts', 'data': state_data}]),
            'ra_trend': self._chart('area', 'Monthly RA billing', monthly[0], [
                {'label': 'Work done', 'data': monthly[1], 'fill': True},
                {'label': 'Net amount', 'data': monthly[2], 'type': 'line'},
            ], unit='money', size='md', allow_toggle=True),
            'backlog': self._chart('bar', 'Value vs billed vs backlog', ['Contract value', 'Cumulative RA', 'Backlog'], [
                {'label': 'Amount', 'data': [round(contract_value or 0.0, 2), round(billed_work or 0.0, 2), round(backlog, 2)]},
            ]),
            'waterfall': self._waterfall_chart(
                ['A Work', 'B Rebate', 'D Material', 'F Sales tax', 'H Mobilization', 'I Retention'],
                [
                    ra_period.get('work') or 0.0,
                    -(ra_period.get('rebate') or 0.0),
                    -(ra_period.get('material') or 0.0),
                    ra_period.get('sales_tax') or 0.0,
                    -(ra_period.get('mobilization') or 0.0),
                    -(ra_period.get('retention') or 0.0),
                ],
                'RA A–I this period',
            ),
            'by_contract': self._chart('bar', 'Value vs billed vs backlog by contract', [row['name'] for row in performance[:8]], [
                {'label': 'Value', 'data': [row.get('value_raw') or 0.0 for row in performance[:8]]},
                {'label': 'RA work', 'data': [row.get('billed_raw') or 0.0 for row in performance[:8]]},
                {'label': 'Backlog', 'data': [row.get('backlog_raw') or 0.0 for row in performance[:8]]},
            ]),
            'by_project': self._backlog_by_project_chart(scope, contract_domain),
            'mobilization': self._chart('bar', 'Mobilization received vs recovered vs outstanding', [
                'Received', 'Recovered on RA', 'Outstanding',
            ], [{'label': 'Amount', 'data': [
                round(mob_received or 0.0, 2), round(mob_recovered or 0.0, 2), round(mob_outstanding, 2),
            ]}]),
            'retention': self._chart('bar', 'Retention withheld vs released vs outstanding', [
                'Withheld on RA', 'Released', 'Outstanding',
            ], [{'label': 'Amount', 'data': [
                round(retention_held or 0.0, 2), round(retention_released or 0.0, 2), round(retention_outstanding, 2),
            ]}]),
            'payment_state': self._chart('doughnut', 'RA invoice payment state', pay_labels, [
                {'label': 'Bills', 'data': pay_data},
            ]),
            'clients': self._chart('bar', 'Top clients by RA work', [row['name'] for row in clients], [
                {'label': 'RA work', 'data': [row['amount'] for row in clients]},
            ]),
        }
        bill_rows = []
        unpaid_rows = []
        missing_rows = []
        if self._can_read('ages.running.bill'):
            cumulative_by_bill = {}
            running_by_contract = {}
            all_bills = self.env['ages.running.bill'].search_fetch(
                self._scope_domain('ages.running.bill', scope, [('state', '!=', 'cancelled')]),
                ['contract_id', 'date', 'value_of_work_done', 'company_id'],
                order='contract_id, date, id',
            )
            for source_bill in all_bills:
                contract_id = source_bill.contract_id.id
                previous = running_by_contract.get(contract_id, 0.0)
                current = self._convert_amount(
                    source_bill.value_of_work_done,
                    source_bill.company_id.currency_id,
                    scope,
                    on_date=source_bill.date,
                    company=source_bill.company_id,
                )
                cumulative = previous + current
                cumulative_by_bill[source_bill.id] = (previous, cumulative)
                running_by_contract[contract_id] = cumulative
            fields_list = [
                'name', 'date', 'net_amount', 'total_receivable', 'value_of_work_done',
                'partner_id', 'state', 'invoice_id', 'invoice_payment_state', 'company_id',
            ]
            bills = self._search_read(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')]) + self._date_domain('date', date_from, date_to),
                fields_list, limit=20, order='date desc',
            )
            for bill in bills:
                partner = bill.get('partner_id')
                company = self.env['res.company'].browse(
                    bill.get('company_id')[0] if bill.get('company_id') else self.env.company.id
                )
                work = self._convert_amount(
                    bill.get('value_of_work_done') or 0.0, company.currency_id, scope,
                    on_date=bill.get('date'), company=company,
                )
                net = self._convert_amount(
                    bill.get('net_amount') or 0.0, company.currency_id, scope,
                    on_date=bill.get('date'), company=company,
                )
                previous, cumulative = cumulative_by_bill.get(bill.get('id'), (0.0, work))
                bill_rows.append({
                    'name': bill.get('name'),
                    'date': self._format_date(bill.get('date')),
                    'partner': partner[1] if partner else '',
                    'work': self._format_money(work, scope),
                    'previous': self._format_money(previous, scope),
                    'cumulative': self._format_money(cumulative, scope),
                    'net': self._format_money(net, scope),
                    'payment': bill.get('invoice_payment_state') or 'no invoice',
                    'res_id': bill.get('id'),
                    'action_key': 'running_bills',
                })
            unpaid_bills = self._search_read(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [
                    ('state', '=', 'confirmed'),
                    ('invoice_payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
                ]),
                fields_list, limit=20, order='date',
            )
            for bill in unpaid_bills:
                partner = bill.get('partner_id')
                unpaid_rows.append({
                    'name': bill.get('name'),
                    'date': self._format_date(bill.get('date')),
                    'partner': partner[1] if partner else '',
                    'payment': bill.get('invoice_payment_state') or '',
                    'net': self._format_money(bill.get('net_amount') or 0.0, scope),
                    'res_id': bill.get('id'),
                    'action_key': 'unpaid_ra',
                })
            missing_bills = self._search_read(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [
                    ('state', '=', 'confirmed'),
                    ('invoice_id', '=', False),
                ]),
                ['name', 'date', 'partner_id', 'net_amount'],
                limit=20, order='date',
            )
            for bill in missing_bills:
                partner = bill.get('partner_id')
                missing_rows.append({
                    'name': bill.get('name'),
                    'date': self._format_date(bill.get('date')),
                    'partner': partner[1] if partner else '',
                    'net': self._format_money(bill.get('net_amount') or 0.0, scope),
                    'res_id': bill.get('id'),
                    'action_key': 'missing_ra_invoices',
                })
        mob_rows = []
        if self._can_read('ages.mobilization.advance'):
            for rec in self._search_read(
                'ages.mobilization.advance',
                self._scope_domain('ages.mobilization.advance', scope, [('state', '=', 'confirmed')]),
                ['name', 'date', 'partner_id', 'mobilization_amount', 'state'],
                limit=15, order='date desc',
            ):
                partner = rec.get('partner_id')
                mob_rows.append({
                    'name': rec.get('name'),
                    'date': self._format_date(rec.get('date')),
                    'partner': partner[1] if partner else '',
                    'amount': self._format_money(rec.get('mobilization_amount') or 0.0, scope),
                    'res_id': rec.get('id'),
                    'action_key': 'mobilization',
                })
        ret_rows = []
        if self._can_read('ages.retention.recovery'):
            for rec in self._search_read(
                'ages.retention.recovery',
                self._scope_domain('ages.retention.recovery', scope, [('state', '=', 'confirmed')]),
                ['name', 'date', 'partner_id', 'retention_amount', 'state'],
                limit=15, order='date desc',
            ):
                partner = rec.get('partner_id')
                ret_rows.append({
                    'name': rec.get('name'),
                    'date': self._format_date(rec.get('date')),
                    'partner': partner[1] if partner else '',
                    'amount': self._format_money(rec.get('retention_amount') or 0.0, scope),
                    'res_id': rec.get('id'),
                    'action_key': 'retention',
                })
        tables = {
            'performance': self._mgmt_table('Contract performance', [
                {'key': 'name', 'label': 'Contract'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'value', 'label': 'Value'},
                {'key': 'billed', 'label': 'RA work'},
                {'key': 'backlog', 'label': 'Backlog'},
            ], performance, 'contracts'),
            'ra_register': self._mgmt_table('Running bills this period', [
                {'key': 'name', 'label': 'Bill'},
                {'key': 'date', 'label': 'Date'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'work', 'label': 'Work'},
                {'key': 'previous', 'label': 'Previous work'},
                {'key': 'cumulative', 'label': 'Cumulative work'},
                {'key': 'net', 'label': 'Net'},
                {'key': 'payment', 'label': 'Invoice payment'},
            ], bill_rows, 'running_bills'),
            'unpaid_ra': self._mgmt_table('Unpaid / partial RA invoices', [
                {'key': 'name', 'label': 'Bill'},
                {'key': 'date', 'label': 'Date'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'payment', 'label': 'Payment'},
                {'key': 'net', 'label': 'Net'},
            ], unpaid_rows, 'unpaid_ra'),
            'missing_invoice': self._mgmt_table('Confirmed RA missing an invoice', [
                {'key': 'name', 'label': 'Bill'},
                {'key': 'date', 'label': 'Date'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'net', 'label': 'Net'},
            ], missing_rows, 'missing_ra_invoices'),
            'mobilization': self._mgmt_table('Mobilization ledger', [
                {'key': 'name', 'label': 'Advance'},
                {'key': 'date', 'label': 'Date'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'amount', 'label': 'Amount'},
            ], mob_rows, 'mobilization'),
            'retention': self._mgmt_table('Retention recovery ledger', [
                {'key': 'name', 'label': 'Recovery'},
                {'key': 'date', 'label': 'Date'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'amount', 'label': 'Amount'},
            ], ret_rows, 'retention'),
            'expiring': self._mgmt_table('Contracts near close date', [
                {'key': 'name', 'label': 'Contract'},
                {'key': 'date_close', 'label': 'Close date'},
                {'key': 'partner', 'label': 'Client'},
            ], [{
                'name': rec.get('name'),
                'date_close': self._format_date(rec.get('date_close')),
                'partner': rec.get('partner_id')[1] if rec.get('partner_id') else '',
                'res_id': rec.get('id'),
                'action_key': 'contracts',
            } for rec in expiring], 'contracts'),
            'overrun': self._mgmt_table('Contracts billed above contract value', [
                {'key': 'name', 'label': 'Contract'},
                {'key': 'partner', 'label': 'Client'},
                {'key': 'value', 'label': 'Value'},
                {'key': 'billed', 'label': 'RA work'},
            ], overrun, 'contracts'),
        }
        warnings = [
            'value_of_work_done is the current bill amount, not cumulative.',
            'Contract total_work_done_value is an integer in the current schema; RA amounts are monetary.',
            'Mobilization/retention outstanding uses confirmed source documents, not reconstructed cash engines.',
        ]
        mob_engine = self._mobilization_engine_payload(scope)
        ret_engine = self._retention_engine_payload(scope)
        if mob_engine:
            tables['mob_engine'] = self._mgmt_table('Mobilization cash engine', [
                {'key': 'name', 'label': 'Line'}, {'key': 'amount', 'label': 'Amount'},
            ], [{
                'name': line.get('name'),
                'amount': self._format_money(line.get('balance') or line.get('amount') or 0.0, scope),
            } for line in (mob_engine.get('lines') or [])[:20] if line.get('line_type') != 'aml'], 'mobilization')
            warnings.append('MobilizationReportEngine cash figures are shown separately from confirmed-document outstanding.')
        if ret_engine:
            tables['ret_engine'] = self._mgmt_table('Retention cash engine', [
                {'key': 'name', 'label': 'Line'}, {'key': 'amount', 'label': 'Amount'},
            ], [{
                'name': line.get('name'),
                'amount': self._format_money(line.get('balance') or line.get('amount') or 0.0, scope),
            } for line in (ret_engine.get('lines') or [])[:20] if line.get('line_type') != 'aml'], 'retention')
            warnings.append('RetentionReportEngine cash figures are shown separately from confirmed-document outstanding.')
        self._attach_sparklines(kpis, {'ra_work': (charts.get('ra_trend'), 0, 'money')})
        return self._payload(
            scope, 'contracts', kpis, charts, tables,
            date_field='ages.running.bill.date', warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['running', 'value', 'ra_work', 'ra_period', 'backlog', 'unpaid_ra'],
                charts=[('waterfall', 12), ('ra_trend', 6), ('clients', 6)],
                tables=['performance', 'unpaid', 'missing', 'expiring'],
            )},
        )

    def _ra_monthly(self, scope, months=6):
        if not self._can_read('ages.running.bill'):
            return [], [], []
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        cursor = date_to.replace(day=1)
        buckets = []
        for _index in range(months):
            buckets.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        buckets.reverse()
        labels, work, net = [], [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            domain = self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')])
            domain += self._date_domain('date', month_start, month_end)
            work.append(round(self._currency_sum(
                'ages.running.bill', domain, 'value_of_work_done', scope,
                date_field='date', company_currency=True,
            ) or 0.0, 2))
            net.append(round(self._currency_sum(
                'ages.running.bill', domain, 'net_amount', scope,
                date_field='date', company_currency=True,
            ) or 0.0, 2))
        return labels, work, net

    def _ra_payment_distribution(self, scope):
        if not self._can_read('ages.running.bill') or not self._has_field('ages.running.bill', 'invoice_payment_state'):
            return [], []
        domain = self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')])
        rows = self.env['ages.running.bill'].read_group(domain, ['id:count'], ['invoice_payment_state'], lazy=False)
        labels = [(row.get('invoice_payment_state') or 'no invoice') for row in rows]
        data = [row.get('invoice_payment_state_count') or row.get('id_count') or 0 for row in rows]
        return labels, data

    def _top_clients(self, scope, limit=8):
        if not self._can_read('ages.running.bill'):
            return []
        domain = self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')])
        return self._currency_grouped(
            'ages.running.bill', domain, 'value_of_work_done', 'partner_id', scope,
            date_field='date', company_currency=True, limit=limit,
        )

    def _contract_performance(self, scope, limit=20):
        contracts = self.env['ages.contract'].search_fetch(
            self._scope_domain('ages.contract', scope),
            ['name', 'partner_id', 'total_work_done_value', 'state', 'company_id', 'date_start'],
            limit=200, order='id desc',
        )
        billed_by_contract = {}
        if self._can_read('ages.running.bill'):
            groups = self._currency_grouped(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [('state', '!=', 'cancelled')]),
                'value_of_work_done', 'contract_id', scope,
                date_field='date', company_currency=True, limit=0,
            )
            for group in groups:
                if group.get('res_id'):
                    billed_by_contract[group['res_id']] = group.get('amount') or 0.0
        performance = []
        overrun = []
        for rec in contracts:
            value = self._convert_amount(
                rec.total_work_done_value, rec.company_id.currency_id, scope,
                on_date=rec.date_start, company=rec.company_id,
            )
            billed = billed_by_contract.get(rec.id) or 0.0
            backlog = max(value - billed, 0.0)
            partner = rec.partner_id
            row = {
                'name': rec.name,
                'partner': partner.display_name if partner else '',
                'value': self._format_money(value, scope),
                'billed': self._format_money(billed, scope),
                'backlog': self._format_money(backlog, scope),
                'value_raw': round(value, 2),
                'billed_raw': round(billed, 2),
                'backlog_raw': round(backlog, 2),
                'res_id': rec.id,
                'action_key': 'contracts',
            }
            if rec.state in ('new', 'running', 'closed'):
                performance.append(row)
            if billed > value and value:
                overrun.append(row)
        performance.sort(key=lambda item: item.get('name') or '')
        return performance[:limit], overrun[:limit]

    def _backlog_by_project_chart(self, scope, contract_domain):
        title = 'Value vs billed vs backlog by project'
        if not self._has_field('ages.contract', 'project_id'):
            return self._chart('bar', title, [], [])
        value_rows = self._currency_grouped(
            'ages.contract', contract_domain, 'total_work_done_value', 'project_id', scope,
            date_field='date_start', company_currency=True, limit=8,
        )
        billed_map = {}
        if self._can_read('ages.running.bill') and self._has_field('ages.running.bill', 'project_id'):
            billed_rows = self._currency_grouped(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [('state', '!=', 'cancelled')]),
                'value_of_work_done', 'project_id', scope,
                date_field='date', company_currency=True, limit=0,
            )
            billed_map = {row.get('res_id'): row.get('amount') or 0.0 for row in billed_rows}
        labels = [row['name'] for row in value_rows]
        values = [round(row.get('amount') or 0.0, 2) for row in value_rows]
        billed = [round(billed_map.get(row.get('res_id')) or 0.0, 2) for row in value_rows]
        backlog = [max(value - billed_amt, 0.0) for value, billed_amt in zip(values, billed)]
        return self._chart('bar', title, labels, [
            {'label': 'Value', 'data': values},
            {'label': 'RA work', 'data': billed},
            {'label': 'Backlog', 'data': backlog},
        ], action_key='projects', group_field='id', label_ids=[row.get('res_id') for row in value_rows])

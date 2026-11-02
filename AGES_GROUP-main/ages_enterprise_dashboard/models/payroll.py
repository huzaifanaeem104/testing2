# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardPayroll(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_payroll_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._capability_map().get('payroll'):
            return self._unavailable(scope, 'payroll', 'Payroll is hidden unless the user has AGES payroll access.')
        date_from, date_to = scope['date_from'], scope['date_to']
        domain = self._scope_domain('hr.payslip', scope) + self._date_domain('date_from', date_from, date_to)
        total = self._search_count('hr.payslip', domain)
        done_domain = domain + [('state', 'in', ('done', 'paid'))]
        net = self._read_group_sum('hr.payslip', done_domain, 'net_wage')
        gross = self._read_group_sum('hr.payslip', done_domain, 'gross_wage') if self._has_field('hr.payslip', 'gross_wage') else 0.0
        basic = self._read_group_sum('hr.payslip', done_domain, 'basic_wage') if self._has_field('hr.payslip', 'basic_wage') else 0.0
        pending = self._search_count('hr.payslip', domain + [('state', 'in', ('draft', 'verify'))])
        paid = self._search_count('hr.payslip', domain + [('state', '=', 'paid')])
        done = self._search_count('hr.payslip', domain + [('state', '=', 'done')])
        unpaid_net = self._read_group_sum('hr.payslip', domain + [('state', '=', 'done')], 'net_wage')
        missing_move = 0
        if self._has_field('hr.payslip', 'move_id'):
            missing_move = self._search_count('hr.payslip', done_domain + [('move_id', '=', False)])
        missing_pay_move = 0
        if self._has_field('hr.payslip', 'payment_move_id'):
            missing_pay_move = self._search_count('hr.payslip', domain + [('state', '=', 'paid'), ('payment_move_id', '=', False)])

        line_totals = {}
        allowance_total = 0.0
        if self._can_read('hr.payslip.line') and self._has_field('hr.payslip.line', 'code'):
            line_domain = self._scope_domain('hr.payslip.line', scope, [
                ('slip_id.state', 'in', ('done', 'paid')),
            ])
            if date_from:
                line_domain.append(('date_from', '>=', date_from))
            if date_to:
                line_domain.append(('date_from', '<=', date_to))
            groups = self.env['hr.payslip.line'].read_group(line_domain, ['total:sum'], ['code'], lazy=False)
            for group in groups:
                line_totals[group.get('code') or ''] = group.get('total') or 0.0
            if self._field_path_exists('hr.payslip.line', 'salary_rule_id.category_id.code'):
                allowance_total = self._read_group_sum(
                    'hr.payslip.line',
                    line_domain + [('salary_rule_id.category_id.code', '=', 'ALW')],
                    'total',
                )

        linked_move = linked_posted_move = 0
        if self._has_field('hr.payslip', 'move_id'):
            linked_move = self._search_count('hr.payslip', done_domain + [('move_id', '!=', False)])
            if self._field_path_exists('hr.payslip', 'move_id.state'):
                linked_posted_move = self._search_count(
                    'hr.payslip', done_domain + [('move_id.state', '=', 'posted')]
                )

        overdue_loans = 0
        loan_amount = 0.0
        today = fields.Date.context_today(self)
        loan_domain = []
        if self._can_read('hr.loan.installment'):
            loan_extra = [
                ('due_date', '<', today),
                ('deduction_state', 'in', ('pending', 'partial')),
            ]
            loan_domain = self._scope_domain('hr.loan.installment', scope, loan_extra)
            overdue_loans = self._search_count('hr.loan.installment', loan_domain)
            residual_field = 'amount_residual' if self._has_field('hr.loan.installment', 'amount_residual') else False
            if residual_field:
                loan_amount = self._read_group_sum('hr.loan.installment', loan_domain, residual_field)

        kpis = [
            self._kpi(scope, 'slips', 'Payslips', total, False, 'payslips', suffix='', basis='count'),
            self._kpi(scope, 'pending', 'Pending payslips', pending, False, 'pending_payslips', suffix='', basis='count'),
            self._kpi(scope, 'done', 'Finalized unpaid (done)', done, False, 'done_payslips', suffix='', basis='count'),
            self._kpi(scope, 'unpaid_net', 'Unpaid finalized net', unpaid_net, False, 'done_payslips',
                      'SUM(net_wage) of payslips in state done (finalized, not paid).'),
            self._kpi(scope, 'paid', 'Paid payslips', paid, False, 'paid_payslips', suffix='', basis='count'),
            self._kpi(scope, 'basic', 'Basic', basic, False, 'finalized_payslips'),
            self._kpi(scope, 'gross', 'Gross', gross, False, 'finalized_payslips'),
            self._kpi(scope, 'net', 'Net', net, False, 'finalized_payslips'),
            self._kpi(scope, 'allowances', 'Allowances (ALW category)', allowance_total, False, 'finalized_payslips',
                      'SUM stored payslip line total where salary-rule category code is ALW.'),
            self._kpi(scope, 'deduction', 'DEDUCTION lines', line_totals.get('DEDUCTION') or 0.0, False, 'finalized_payslips',
                      'SUM(hr.payslip.line.total) where code=DEDUCTION on done/paid slips.'),
            self._kpi(scope, 'advance', 'ADVANCE lines', line_totals.get('ADVANCE') or 0.0, False, 'finalized_payslips'),
            self._kpi(scope, 'loan', 'LOAN lines', line_totals.get('LOAN') or 0.0, False, 'finalized_payslips'),
            self._kpi(scope, 'expenses', 'EXPENSES lines', line_totals.get('EXPENSES') or 0.0, False, 'finalized_payslips'),
            self._kpi(scope, 'linked_move', 'Finalized slips with JE', linked_move, False, 'finalized_payslips', suffix='', basis='count'),
            self._kpi(scope, 'posted_move', 'Finalized slips with posted JE', linked_posted_move, False, 'finalized_payslips', suffix='', basis='count'),
            self._kpi(scope, 'missing_move', 'Finalized slips without JE', missing_move, False, 'payslips_missing_move', suffix='', basis='count'),
            self._kpi(scope, 'missing_pay', 'Paid slips without payment move', missing_pay_move, False, 'payslips_missing_payment', suffix='', basis='count'),
            self._kpi(scope, 'overdue_loans', 'Overdue loan installments', overdue_loans, False, 'overdue_loan_installments', suffix='', basis='count') if self._can_read('hr.loan.installment') else self._unavailable_kpi(scope, 'overdue_loans', 'Overdue loan installments', 'hr.loan.installment is not readable.'),
            self._kpi(scope, 'overdue_loan_amt', 'Overdue loan residual', loan_amount, False, 'overdue_loan_installments') if self._can_read('hr.loan.installment') else self._unavailable_kpi(scope, 'overdue_loan_amt', 'Overdue loan residual', 'hr.loan.installment is not readable.'),
        ]
        if self._has_field('hr.leave', 'payslip_state'):
            blocked_leaves = self._search_count(
                'hr.leave',
                self._scope_domain('hr.leave', scope, [('payslip_state', '=', 'blocked')]),
            )
            kpis.append(self._kpi(
                scope, 'leave_blocked', 'Leave blocked from current payroll', blocked_leaves, False,
                'leave_payroll_blocked',
                'hr.leave rows whose stored payslip_state is blocked.',
                suffix='', basis='count',
            ))
        charts = {
            'states': self._group_chart('hr.payslip', domain, 'state', 'Payslip state'),
            'components': self._chart('doughnut', 'Salary component composition (line codes)', list(line_totals.keys())[:12], [
                {'label': 'Total', 'data': [round(line_totals[key], 2) for key in list(line_totals.keys())[:12]]},
            ]),
        }
        if self._has_field('hr.payslip', 'department_id'):
            charts['departments'] = self._group_chart('hr.payslip', done_domain, 'department_id', 'Net payroll by department', 'horizontalBar', value_field='net_wage')
        if self._has_field('hr.payslip', 'project_id'):
            charts['projects'] = self._group_chart('hr.payslip', done_domain, 'project_id', 'Net payroll by project', 'bar', value_field='net_wage')
        monthly = self._payroll_monthly(scope)
        charts['trend'] = self._chart('mixed', 'Monthly gross/net', monthly[0], [
            {'label': 'Gross', 'data': monthly[1], 'type': 'bar'},
            {'label': 'Net', 'data': monthly[2], 'type': 'line'},
        ], unit='money', size='lg', allow_toggle=True)
        charts['recovery'] = self._chart('bar', 'Loans / advances / expenses recovered', ['LOAN', 'ADVANCE', 'EXPENSES', 'DEDUCTION'], [
            {'label': 'Line total', 'data': [
                round(line_totals.get('LOAN') or 0.0, 2),
                round(line_totals.get('ADVANCE') or 0.0, 2),
                round(line_totals.get('EXPENSES') or 0.0, 2),
                round(line_totals.get('DEDUCTION') or 0.0, 2),
            ]},
        ])
        tables = {
            'payslips': self._mgmt_table('Payslips', [
                {'key': 'number', 'label': 'Number'}, {'key': 'employee', 'label': 'Employee'},
                {'key': 'state', 'label': 'State'}, {'key': 'net', 'label': 'Net'},
            ], self._document_rows(
                'hr.payslip', domain,
                {'number': 'number', 'employee': 'employee_id', 'state': 'state', 'net': 'net_wage'},
                'payslips', order='date_from desc', money_fields=('net_wage',), scope=scope,
            ), 'payslips'),
            'pending': self._mgmt_table('Pending payslips', [
                {'key': 'number', 'label': 'Number'}, {'key': 'employee', 'label': 'Employee'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'hr.payslip', domain + [('state', 'in', ('draft', 'verify'))],
                {'number': 'number', 'employee': 'employee_id', 'state': 'state'},
                'pending_payslips', order='date_from', scope=scope,
            ), 'pending_payslips'),
            'unpaid': self._mgmt_table('Unpaid finalized payslips', [
                {'key': 'number', 'label': 'Number'}, {'key': 'employee', 'label': 'Employee'}, {'key': 'net', 'label': 'Net'},
            ], self._document_rows(
                'hr.payslip', domain + [('state', '=', 'done')],
                {'number': 'number', 'employee': 'employee_id', 'net': 'net_wage'},
                'done_payslips', money_fields=('net_wage',), scope=scope,
            ), 'done_payslips'),
            'missing_move': self._mgmt_table('Missing journal entry', [
                {'key': 'number', 'label': 'Number'}, {'key': 'employee', 'label': 'Employee'},
            ], self._document_rows(
                'hr.payslip', done_domain + [('move_id', '=', False)] if self._has_field('hr.payslip', 'move_id') else [('id', '=', 0)],
                {'number': 'number', 'employee': 'employee_id'},
                'payslips_missing_move', scope=scope,
            ), 'payslips_missing_move'),
            'missing_payment': self._mgmt_table('Missing payment move', [
                {'key': 'number', 'label': 'Number'}, {'key': 'employee', 'label': 'Employee'},
            ], self._document_rows(
                'hr.payslip',
                domain + [('state', '=', 'paid'), ('payment_move_id', '=', False)]
                if self._has_field('hr.payslip', 'payment_move_id') else [('id', '=', 0)],
                {'number': 'number', 'employee': 'employee_id'},
                'payslips_missing_payment', scope=scope,
            ), 'payslips_missing_payment'),
            'dept_summary': self._payroll_group_table(scope, done_domain, 'department_id', 'Department payroll summary'),
            'project_summary': self._payroll_group_table(scope, done_domain, 'project_id', 'Project payroll summary'),
        }
        if self._can_read('hr.payslip.run'):
            tables['batches'] = self._mgmt_table('Payslip batches', [
                {'key': 'name', 'label': 'Batch'}, {'key': 'state', 'label': 'State'}, {'key': 'start', 'label': 'From'}, {'key': 'end', 'label': 'To'},
            ], self._document_rows(
                'hr.payslip.run', self._scope_domain('hr.payslip.run', scope),
                {'name': 'name', 'state': 'state', 'start': 'date_start', 'end': 'date_end'},
                'payslip_runs', order='date_end desc', date_fields=('date_start', 'date_end'), scope=scope,
            ), 'payslip_runs')
        if self._has_field('hr.leave', 'payslip_state'):
            tables['leave_blocked'] = self._mgmt_table('Leave blocked from current payroll', [
                {'key': 'name', 'label': 'Leave'}, {'key': 'employee', 'label': 'Employee'},
                {'key': 'from', 'label': 'From'}, {'key': 'state', 'label': 'Payslip state'},
            ], self._document_rows(
                'hr.leave',
                self._scope_domain('hr.leave', scope, [('payslip_state', '=', 'blocked')]),
                {'name': 'name', 'employee': 'employee_id', 'from': 'date_from', 'state': 'payslip_state'},
                'leave_payroll_blocked', order='date_from', date_fields=('date_from',), scope=scope,
            ), 'leave_payroll_blocked')
        if self._can_read('hr.loan.installment'):
            tables['loans'] = self._mgmt_table('Overdue loan installments', [
                {'key': 'name', 'label': 'Installment'}, {'key': 'employee', 'label': 'Employee'},
                {'key': 'due', 'label': 'Due'}, {'key': 'residual', 'label': 'Residual'},
            ], self._document_rows(
                'hr.loan.installment',
                loan_domain,
                {'name': 'name', 'employee': 'employee_id', 'due': 'due_date', 'residual': 'amount_residual'},
                'overdue_loan_installments', order='due_date', money_fields=('amount_residual',), date_fields=('due_date',), scope=scope,
            ), 'overdue_loan_installments')
        if self._has_field('hr.payslip', 'move_id'):
            recon_rows = []
            slips = self.env['hr.payslip'].search(done_domain + [('move_id', '!=', False)], limit=20, order='date_from desc')
            for slip in slips:
                move = slip.move_id
                recon_rows.append({
                    'number': slip.number or '',
                    'employee': slip.employee_id.display_name if slip.employee_id else '',
                    'net': self._format_money(slip.net_wage or 0.0, scope),
                    'move': move.display_name if move else '',
                    'move_state': move.state if move else '',
                    'res_id': slip.id,
                    'action_key': 'finalized_payslips',
                })
            tables['je_recon'] = self._mgmt_table(
                'Payslip vs journal entry (side-by-side, not a forced match)',
                [
                    {'key': 'number', 'label': 'Payslip'}, {'key': 'employee', 'label': 'Employee'},
                    {'key': 'net', 'label': 'Net'}, {'key': 'move', 'label': 'Journal entry'},
                    {'key': 'move_state', 'label': 'JE state'},
                ],
                recon_rows,
                'finalized_payslips',
                empty='No finalized payslips with a journal entry in this scope.',
            )
        warnings = [
            'Salary components use stored payslip-line codes (BASIC, GROSS, DEDUCTION, NET, ADVANCE, LOAN, EXPENSES) when those lines exist.',
            'category_id on payslip lines is related and not grouped.',
        ]
        self._attach_sparklines(kpis, {'net': (charts.get('trend'), 1, 'money'), 'gross': (charts.get('trend'), 0, 'money')})
        return self._payload(
            scope, 'payroll', kpis, charts, tables,
            date_field='hr.payslip.date_from', warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['slips', 'pending', 'net', 'unpaid_net', 'missing_move', 'overdue_loans'],
                charts=[('trend', 8), ('departments', 4), ('recovery', 6), ('projects', 6)],
                tables=['pending', 'unpaid', 'missing_move', 'loans'],
            )},
        )

    def _payroll_monthly(self, scope, months=6):
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        cursor = date_to.replace(day=1)
        buckets = []
        for _index in range(months):
            buckets.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        buckets.reverse()
        labels, gross, net = [], [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            domain = self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))]) + self._date_domain('date_from', month_start, month_end)
            gross.append(round(self._read_group_sum('hr.payslip', domain, 'gross_wage') or 0.0, 2) if self._has_field('hr.payslip', 'gross_wage') else 0.0)
            net.append(round(self._read_group_sum('hr.payslip', domain, 'net_wage') or 0.0, 2))
        return labels, gross, net

    def _payroll_group_table(self, scope, domain, groupby, title):
        if not self._has_field('hr.payslip', groupby):
            return self._mgmt_table(title, [], [], 'payslips', empty='%s is not present on payslips.' % groupby)
        spec = ['net_wage:sum']
        if self._has_field('hr.payslip', 'gross_wage'):
            spec.append('gross_wage:sum')
        try:
            groups = self.env['hr.payslip'].read_group(domain, spec, [groupby], lazy=False)
        except Exception:
            groups = []
        rows = []
        for group in groups[:20]:
            raw = group.get(groupby)
            rows.append({
                'name': raw[1] if isinstance(raw, (list, tuple)) and raw else (raw or 'Unassigned'),
                'gross': self._format_money(group.get('gross_wage') or 0.0, scope),
                'net': self._format_money(group.get('net_wage') or 0.0, scope),
                'res_id': raw[0] if isinstance(raw, (list, tuple)) and raw else False,
                'res_field': groupby,
                'action_key': 'payslips',
            })
        return self._mgmt_table(title, [
            {'key': 'name', 'label': 'Group'}, {'key': 'gross', 'label': 'Gross'}, {'key': 'net', 'label': 'Net'},
        ], rows, 'payslips')

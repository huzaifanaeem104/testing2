# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardHr(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_hr_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._capability_map().get('hr'):
            return self._unavailable(scope, 'hr', 'HR officer or manager access is required.')
        domain = self._scope_domain('hr.employee', scope)
        date_from, date_to = scope['date_from'], scope['date_to']
        total = self._search_count('hr.employee', domain)
        active = self._search_count('hr.employee', domain + [('active', '=', True)])
        inactive = self._search_count('hr.employee', domain + [('active', '=', False)])
        contracts = expiring = 0
        contract_domain = self._scope_domain('hr.contract', scope)
        hr_contract_horizon = max(
            self._config_int('ages_enterprise_dashboard.hr_contract_expiry_days', 30), 0
        )
        if self._can_read('hr.contract'):
            contracts = self._search_count('hr.contract', contract_domain + [('state', '=', 'open')])
            if self._has_field('hr.contract', 'date_end'):
                horizon = (scope['date_to'] or fields.Date.context_today(self)) + timedelta(days=hr_contract_horizon)
                expiring = self._search_count('hr.contract', contract_domain + [
                    ('state', '=', 'open'), ('date_end', '!=', False), ('date_end', '<=', horizon),
                ])
        hires = exits = 0
        if self._has_field('hr.employee', 'create_date') and date_from and date_to:
            hires = self._search_count('hr.employee', domain + [
                ('create_date', '>=', '%s 00:00:00' % date_from),
                ('create_date', '<=', '%s 23:59:59' % date_to),
            ])
        if self._has_field('hr.employee', 'departure_date') and date_from:
            exits = self._search_count('hr.employee', domain + [
                ('departure_date', '>=', date_from), ('departure_date', '<=', date_to),
            ])
        transfers = wages = leaves = 0
        if self._can_read('hr.employee.project.tracking'):
            tdomain = self._scope_domain('hr.employee.project.tracking', scope)
            tdomain += self._typed_date_domain(
                'hr.employee.project.tracking', 'date', date_from, date_to
            )
            transfers = self._search_count('hr.employee.project.tracking', tdomain)
        payroll_ok = self._capability_map().get('payroll') or self._user_in_group('hr.group_hr_user') or self._user_in_group('hr.group_hr_manager')
        if payroll_ok and self._can_read('hr.employee.wage.history'):
            wdomain = self._scope_domain('hr.employee.wage.history', scope)
            wdomain += self._typed_date_domain(
                'hr.employee.wage.history', 'date', date_from, date_to
            )
            wages = self._search_count('hr.employee.wage.history', wdomain)
        if self._can_read('hr.leave'):
            leaves = self._search_count(
                'hr.leave',
                self._scope_domain('hr.leave', scope) + self._typed_date_domain(
                    'hr.leave', 'date_from', date_from, date_to
                ),
            )
        unassigned_dept = self._search_count('hr.employee', domain + [('active', '=', True), ('department_id', '=', False)]) if self._has_field('hr.employee', 'department_id') else 0
        unassigned_project = self._search_count('hr.employee', domain + [('active', '=', True), ('project_id', '=', False)]) if self._has_field('hr.employee', 'project_id') else 0

        kpis = [
            self._kpi(scope, 'total', 'Employees', total, False, 'employees', suffix='', basis='count'),
            self._kpi(scope, 'active', 'Active', active, False, 'active_employees', suffix='', basis='count'),
            self._kpi(scope, 'inactive', 'Inactive', inactive, False, 'inactive_employees', suffix='', basis='count'),
            self._kpi(scope, 'contracts', 'Open contracts', contracts, False, 'hr_contracts', suffix='', basis='count'),
            self._kpi(scope, 'expiring', 'Contracts nearing end', expiring, False, 'expiring_hr_contracts',
                      'Open hr.contract with date_end inside the configured horizon.', suffix='', basis='count'),
            self._kpi(scope, 'hires', 'New employee records', hires, False, 'new_hires',
                      'Count of hr.employee whose create_date is in the period. Not a dedicated hire-date field.', suffix='', basis='count'),
            self._kpi(scope, 'exits', 'Departures', exits, False, 'employee_departures',
                      'Uses departure_date when that field exists.', suffix='', basis='count') if self._has_field('hr.employee', 'departure_date') else self._unavailable_kpi(scope, 'exits', 'Departures', 'hr.employee.departure_date is not present.'),
            self._kpi(scope, 'transfers', 'Project transfers', transfers, False, 'employee_transfers', suffix='', basis='count'),
            self._kpi(scope, 'wages', 'Wage-change records', wages, False, 'wage_changes',
                      'Hidden unless HR/payroll access exists.', suffix='', basis='count') if payroll_ok else self._unavailable_kpi(scope, 'wages', 'Wage-change activity', 'Wage history is restricted to HR/payroll users.'),
            self._kpi(scope, 'leaves', 'Leave records', leaves, False, 'leave_records', suffix='', basis='count') if self._can_read('hr.leave') else self._unavailable_kpi(scope, 'leaves', 'Leave activity', 'hr.leave is not readable or not installed.'),
            self._kpi(scope, 'no_dept', 'No department', unassigned_dept, False, 'employees_no_department', suffix='', basis='count'),
            self._kpi(scope, 'no_project', 'No project', unassigned_project, False, 'employees_no_project', suffix='', basis='count'),
        ]
        charts = {}
        if self._has_field('hr.employee', 'department_id'):
            charts['departments'] = self._group_chart('hr.employee', domain + [('active', '=', True)], 'department_id', 'Headcount by department')
        if self._has_field('hr.employee', 'job_id'):
            charts['jobs'] = self._group_chart('hr.employee', domain + [('active', '=', True)], 'job_id', 'Headcount by job')
        if self._has_field('hr.employee', 'project_id'):
            charts['projects'] = self._group_chart('hr.employee', domain + [('active', '=', True)], 'project_id', 'Headcount by project')
        if self._has_field('hr.employee', 'ages_employee_category'):
            charts['category'] = self._group_chart('hr.employee', domain + [('active', '=', True)], 'ages_employee_category', 'Staff / site / labor')
        hire_labels, hire_data = self._monthly_model_count('hr.employee', scope, [], 'create_date') if self._has_field('hr.employee', 'create_date') else ([], [])
        if hire_labels:
            charts['hires'] = self._chart('bar', 'New employee records by month', hire_labels, [{'label': 'New records', 'data': hire_data}])
        if self._has_field('hr.employee', 'departure_date'):
            exit_labels, exit_data = self._monthly_model_count('hr.employee', scope, [], 'departure_date')
            if hire_labels and exit_labels == hire_labels:
                charts['hires'] = self._chart('bar', 'New employee records vs departures', hire_labels, [
                    {'label': 'New records', 'data': hire_data},
                    {'label': 'Departures', 'data': exit_data},
                ])
            else:
                charts['exits'] = self._chart('bar', 'Departures by month', exit_labels, [{'label': 'Exits', 'data': exit_data}])
        if self._can_read('hr.employee.project.tracking') and self._has_field('hr.employee.project.tracking', 'date'):
            charts['transfers'] = self._chart('bar', 'Project transfer trend', *self._monthly_model_count('hr.employee.project.tracking', scope, [], 'date'))
        tables = {
            'employees': self._mgmt_table('Employees', [
                {'key': 'name', 'label': 'Employee'}, {'key': 'department', 'label': 'Department'},
                {'key': 'job', 'label': 'Job'}, {'key': 'project', 'label': 'Project'},
            ], self._document_rows(
                'hr.employee', domain + [('active', '=', True)],
                {'name': 'name', 'department': 'department_id', 'job': 'job_id', 'project': 'project_id'},
                'employees', order='name', scope=scope,
            ), 'employees'),
            'unassigned': self._mgmt_table('Unassigned department or project', [
                {'key': 'name', 'label': 'Employee'}, {'key': 'department', 'label': 'Department'}, {'key': 'project', 'label': 'Project'},
            ], self._document_rows(
                'hr.employee',
                domain + [('active', '=', True)] + ['|', ('department_id', '=', False), ('project_id', '=', False)] if self._has_field('hr.employee', 'project_id') else domain + [('department_id', '=', False)],
                {'name': 'name', 'department': 'department_id', 'project': 'project_id'},
                'employees', order='name', scope=scope,
            ), 'employees'),
        }
        if self._can_read('hr.employee.project.tracking'):
            tables['transfers'] = self._mgmt_table('Project transfers', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'project', 'label': 'Project'}, {'key': 'date', 'label': 'Date'},
            ], self._document_rows(
                'hr.employee.project.tracking', tdomain,
                {'employee': 'employee_id', 'project': 'project_id', 'date': 'date'},
                'employee_transfers', order='date desc', date_fields=('date',), scope=scope,
            ), 'employee_transfers')
        if self._can_read('hr.contract') and self._has_field('hr.contract', 'date_end'):
            tables['expiry'] = self._mgmt_table('Contracts nearing end', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'end', 'label': 'End date'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'hr.contract',
                contract_domain + [('state', '=', 'open'), ('date_end', '!=', False), ('date_end', '<=', (scope['date_to'] or fields.Date.context_today(self)) + timedelta(days=hr_contract_horizon))],
                {'employee': 'employee_id', 'end': 'date_end', 'state': 'state'},
                'expiring_hr_contracts', order='date_end', date_fields=('date_end',), scope=scope,
            ), 'expiring_hr_contracts')
        if payroll_ok and self._can_read('hr.employee.wage.history'):
            tables['wages'] = self._mgmt_table('Recent wage changes', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'old', 'label': 'Old'}, {'key': 'new', 'label': 'New'},
            ], self._document_rows(
                'hr.employee.wage.history',
                self._scope_domain('hr.employee.wage.history', scope) + self._typed_date_domain(
                    'hr.employee.wage.history', 'date', date_from, date_to
                ),
                {'employee': 'employee_id', 'old': 'old_wage', 'new': 'new_wage'},
                'wage_changes', order='date desc', money_fields=('old_wage', 'new_wage'), scope=scope,
            ), 'wage_changes')
        elif not payroll_ok:
            tables['wages'] = self._mgmt_table('Recent wage changes', [], [], empty='Wage history is restricted to HR/payroll users.')
        if scope.get('employee_ids') and self._can_read('hr.employee'):
            employee_domain = domain + [('id', 'in', scope['employee_ids'])]
            tables['employee_360'] = self._mgmt_table('Employee 360', [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'department', 'label': 'Department'},
                {'key': 'job', 'label': 'Job'},
                {'key': 'project', 'label': 'Project'},
            ], self._document_rows(
                'hr.employee', employee_domain,
                {'name': 'name', 'department': 'department_id', 'job': 'job_id', 'project': 'project_id'},
                'employees', order='name', scope=scope,
            ), 'employees')
            if self._can_read('hr.attendance'):
                att_domain = self._scope_domain('hr.attendance', scope) + self._datetime_date_domain('check_in', date_from, date_to)
                hours = self._read_group_sum('hr.attendance', att_domain, 'worked_hours') if self._has_field('hr.attendance', 'worked_hours') else 0.0
                kpis.append(self._kpi(scope, 'emp_hours', 'Selected employee hours', hours, False, 'attendances', suffix='', basis='count'))
            if self._capability_map().get('payroll'):
                payroll = self._read_group_sum(
                    'hr.payslip',
                    self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))]) + self._date_domain('date_from', date_from, date_to),
                    'net_wage',
                )
                kpis.append(self._kpi(scope, 'emp_payroll', 'Selected employee payroll net', payroll, False, 'payslips'))
        warnings = [
            'Portal labour filters use hr.department. ages_employee_category is staff/site/labor and is not a department.',
            'New-hire count uses create_date because a dedicated hire-date field is not assumed.',
        ]
        return self._payload(
            scope, 'hr', kpis, charts, tables, warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['active', 'contracts', 'expiring', 'hires', 'exits', 'no_dept'],
                charts=[('departments', 4), ('hires', 8), ('category', 6), ('projects', 6)],
                tables=['employees', 'expiry'],
            )},
        )

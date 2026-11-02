# -*- coding: utf-8 -*-

from odoo import models


class AgesEnterpriseDashboardExpenses(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_expenses_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        has_ages = self._can_read('ages.expense')
        has_hr = self._can_read('hr.expense')
        if not has_ages and not has_hr:
            return self._unavailable(scope, 'expenses', 'No expense model is readable.')
        date_from, date_to = scope['date_from'], scope['date_to']
        kpis = []
        warnings = [
            'AGES vendor expenses and standard employee expenses are separate domains and are not added together.',
            'Do not add ages.expense totals to executive accounting expense; posted AML is the executive source.',
        ]
        charts = {}
        tables = {}
        if has_ages:
            domain = self._scope_domain('ages.expense', scope) + self._date_domain('date', date_from, date_to)
            total = self._search_count('ages.expense', domain)
            amount = self._read_group_sum('ages.expense', domain, 'total_amount')
            approved = self._read_group_sum('ages.expense', domain + [('state', '=', 'approved')], 'total_amount')
            pending = self._search_count('ages.expense', domain + [('state', 'in', ('new', 'confirmed'))])
            paid = 0.0
            outstanding = 0.0
            if self._has_field('ages.expense', 'payment_id'):
                paid = self._read_group_sum('ages.expense', domain + [('state', '=', 'approved'), ('payment_id', '!=', False)], 'total_amount')
                outstanding = self._read_group_sum('ages.expense', domain + [('state', '=', 'approved'), ('payment_id', '=', False)], 'total_amount')
            kpis.extend([
                self._kpi(scope, 'ages_count', 'AGES expense documents', total, False, 'ages_expenses', suffix='', basis='count'),
                self._kpi(scope, 'ages_amount', 'AGES expense amount', amount, False, 'ages_expenses'),
                self._kpi(scope, 'ages_approved', 'Approved AGES expenses', approved, False, 'ages_expenses'),
                self._kpi(scope, 'ages_pending', 'Pending AGES expenses', pending, False, 'ages_expenses', suffix='', basis='count'),
                self._kpi(scope, 'ages_paid', 'Approved with payment', paid, False, 'ages_expenses',
                          'Approved documents whose payment_id is set.'),
                self._kpi(scope, 'ages_outstanding', 'Approved without payment', outstanding, False, 'ages_expenses'),
            ])
            charts['ages_states'] = self._group_chart('ages.expense', domain, 'state', 'AGES expenses by state', value_field='total_amount')
            ages_trend = self._monthly_model_sum(
                'ages.expense', scope, [], 'date', 'total_amount',
            )
            charts['ages_trend'] = self._chart(
                'area', 'Monthly AGES expense', ages_trend[0],
                [{'label': 'Amount', 'data': ages_trend[1]}],
                unit='money', allow_toggle=True,
            )
            if self._has_field('ages.expense', 'vendor_id'):
                charts['vendors'] = self._group_chart('ages.expense', domain, 'vendor_id', 'Expense by vendor', 'bar', value_field='total_amount')
            if self._has_field('ages.expense', 'project_id'):
                charts['projects'] = self._group_chart('ages.expense', domain, 'project_id', 'Expense by project', 'bar', value_field='total_amount')
            if self._has_field('ages.expense', 'sub_company_id'):
                charts['sub'] = self._group_chart('ages.expense', domain, 'sub_company_id', 'Expense by active company', 'bar', value_field='total_amount')
            if self._can_read('ages.expense.line') and self._has_field('ages.expense.line', 'account_id'):
                line_domain = self._scope_domain('ages.expense.line', scope)
                if self._field_path_exists('ages.expense.line', 'expense_id.date'):
                    line_domain += self._date_domain('expense_id.date', date_from, date_to)
                charts['accounts'] = self._group_chart('ages.expense.line', line_domain, 'account_id', 'Expense by account', 'doughnut', value_field='amount' if self._has_field('ages.expense.line', 'amount') else False)
            tables['ages'] = self._mgmt_table('AGES expenses', [
                {'key': 'name', 'label': 'Expense'}, {'key': 'date', 'label': 'Date'},
                {'key': 'vendor', 'label': 'Vendor'}, {'key': 'state', 'label': 'State'}, {'key': 'amount', 'label': 'Amount'},
            ], self._document_rows(
                'ages.expense', domain,
                {'name': 'name', 'date': 'date', 'vendor': 'vendor_id', 'state': 'state', 'amount': 'total_amount'},
                'ages_expenses', order='date desc', money_fields=('total_amount',), date_fields=('date',), scope=scope,
            ), 'ages_expenses')
            tables['pending'] = self._mgmt_table('Pending approvals', [
                {'key': 'name', 'label': 'Expense'}, {'key': 'date', 'label': 'Date'}, {'key': 'amount', 'label': 'Amount'},
            ], self._document_rows(
                'ages.expense', domain + [('state', 'in', ('new', 'confirmed'))],
                {'name': 'name', 'date': 'date', 'amount': 'total_amount'},
                'ages_expenses', order='date', money_fields=('total_amount',), date_fields=('date',), scope=scope,
            ), 'ages_expenses')
            tables['unpaid'] = self._mgmt_table('Unpaid approved expenses', [
                {'key': 'name', 'label': 'Expense'}, {'key': 'vendor', 'label': 'Vendor'}, {'key': 'amount', 'label': 'Amount'},
            ], self._document_rows(
                'ages.expense', domain + [('state', '=', 'approved'), ('payment_id', '=', False)] if self._has_field('ages.expense', 'payment_id') else [('id', '=', 0)],
                {'name': 'name', 'vendor': 'vendor_id', 'amount': 'total_amount'},
                'ages_expenses', money_fields=('total_amount',), scope=scope,
            ), 'ages_expenses')
            high = self._search_read('ages.expense', domain, ['name', 'total_amount', 'vendor_id', 'date'], limit=15, order='total_amount desc')
            tables['high'] = self._mgmt_table('High-value expenses', [
                {'key': 'name', 'label': 'Expense'}, {'key': 'vendor', 'label': 'Vendor'}, {'key': 'amount', 'label': 'Amount'},
            ], [{
                'name': rec.get('name'),
                'vendor': rec.get('vendor_id')[1] if rec.get('vendor_id') else '',
                'amount': self._format_money(rec.get('total_amount') or 0.0, scope),
                'res_id': rec.get('id'),
                'action_key': 'ages_expenses',
            } for rec in high], 'ages_expenses')
        if has_hr:
            domain = self._scope_domain('hr.expense', scope) + self._date_domain('date', date_from, date_to)
            total = self._search_count('hr.expense', domain)
            amount_field = 'total_amount' if self._has_field('hr.expense', 'total_amount') else 'untaxed_amount'
            amount = self._read_group_sum('hr.expense', domain, amount_field) if self._has_field('hr.expense', amount_field) else 0.0
            kpis.extend([
                self._kpi(scope, 'hr_count', 'Employee expenses', total, False, 'hr_expenses', suffix='', basis='count'),
                self._kpi(scope, 'hr_amount', 'Employee expense amount', amount, False, 'hr_expenses'),
            ])
            if self._has_field('hr.expense', 'state'):
                charts['hr_states'] = self._group_chart('hr.expense', domain, 'state', 'Employee expenses by state', value_field=amount_field if self._has_field('hr.expense', amount_field) else False)
        else:
            kpis.append(self._unavailable_kpi(
                scope, 'hr_expense', 'Employee reimbursement metrics',
                'hr.expense is not installed. Only AGES vendor/cash expenses are shown.',
            ))
        ages_amount = next((kpi.get('value') or 0.0 for kpi in kpis if kpi.get('key') == 'ages_amount'), 0.0)
        hr_amount = next((kpi.get('value') or 0.0 for kpi in kpis if kpi.get('key') == 'hr_amount'), 0.0)
        charts['compare'] = self._chart(
            'bar', 'AGES vs employee expenses',
            ['AGES expenses', 'Employee expenses'],
            [{'label': 'Amount', 'data': [round(ages_amount or 0.0, 2), round(hr_amount or 0.0, 2)]}],
            unit='money', subtitle='Different documents; never summed',
        )
        self._attach_sparklines(kpis, {'ages_amount': (charts.get('ages_trend'), 0, 'money')})
        return self._payload(
            scope, 'expenses', kpis, charts, tables,
            date_field='ages.expense.date', warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['ages_amount', 'ages_pending', 'ages_outstanding', 'hr_amount'],
                charts=[('compare', 6), ('ages_trend', 6), ('ages_states', 6), ('hr_states', 6)],
                tables=['high'],
            )},
        )

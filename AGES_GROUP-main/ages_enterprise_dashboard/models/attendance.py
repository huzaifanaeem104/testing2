# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesEnterpriseDashboardAttendance(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_attendance_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._can_read('hr.attendance') and not self._can_read('project.portal.attendance'):
            return self._unavailable(scope, 'attendance', 'Attendance records are not readable.')
        date_from, date_to = scope['date_from'], scope['date_to']
        att_count = present = missing_out = 0
        hours = overtime = 0.0
        domain = []
        if self._can_read('hr.attendance'):
            domain = self._scope_domain('hr.attendance', scope)
            domain += self._datetime_date_domain('check_in', date_from, date_to)
            att_count = self._search_count('hr.attendance', domain)
            present = self._distinct_count('hr.attendance', domain, 'employee_id')
            if self._has_field('hr.attendance', 'worked_hours'):
                hours = self._read_group_sum('hr.attendance', domain, 'worked_hours')
            ot_field = 'validated_overtime_hours' if self._has_field('hr.attendance', 'validated_overtime_hours') else False
            if ot_field:
                overtime = self._read_group_sum('hr.attendance', domain, ot_field)
            missing_out = self._search_count('hr.attendance', domain + [('check_out', '=', False)])
        portal_draft = portal_failed = portal_confirmed = portal_absent = 0
        if self._can_read('project.portal.attendance'):
            pdomain = self._scope_domain('project.portal.attendance', scope) + self._date_domain('date', date_from, date_to)
            portal_confirmed = self._search_count('project.portal.attendance', pdomain + [('state', '=', 'confirmed')])
            portal_draft = self._search_count('project.portal.attendance', pdomain + [('state', '=', 'draft')])
            if self._has_field('project.portal.attendance', 'sync_state'):
                portal_failed = self._search_count('project.portal.attendance', pdomain + [('sync_state', '=', 'failed')])
            if self._has_field('project.portal.attendance', 'work_entry_type'):
                portal_absent = self._search_count('project.portal.attendance', pdomain + [('work_entry_type', '=', 'absent')])
        we_conflict = we_draft = we_validated = 0
        if self._can_read('hr.work.entry') and self._has_field('hr.work.entry', 'state'):
            wed = self._scope_domain('hr.work.entry', scope)
            wed += self._typed_date_domain('hr.work.entry', 'date_start', date_from, date_to)
            we_conflict = self._search_count('hr.work.entry', wed + [('state', '=', 'conflict')])
            we_draft = self._search_count('hr.work.entry', wed + [('state', '=', 'draft')])
            we_validated = self._search_count('hr.work.entry', wed + [('state', '=', 'validated')])
        kpis = [
            self._kpi(scope, 'attendance', 'Attendance records', att_count, False, 'attendances', suffix='', basis='count'),
            self._kpi(scope, 'present', 'Employees present', present, False, 'attendances',
                      'Distinct employee_id on hr.attendance in the period.', suffix='', basis='count'),
            self._kpi(scope, 'hours', 'Worked hours', hours, False, 'attendances', suffix='', basis='count',
                      date_field='hr.attendance.check_in', formula='SUM(worked_hours) on synced attendance.'),
            self._kpi(scope, 'overtime', 'Validated overtime hours', overtime, False, 'attendances', suffix='', basis='count') if self._has_field('hr.attendance', 'validated_overtime_hours') else self._unavailable_kpi(scope, 'overtime', 'Overtime hours', 'validated_overtime_hours is not present on hr.attendance.'),
            self._unavailable_kpi(scope, 'late', 'Late arrival / early departure',
                                  'No stored schedule comparison exists. Attendance rate is also unavailable without a roster denominator.'),
            self._kpi(scope, 'missing_out', 'Missing check-out', missing_out, False, 'missing_checkouts', suffix='', basis='count'),
            self._kpi(scope, 'portal_confirmed', 'Portal confirmed', portal_confirmed, False, 'portal_attendance', suffix='', basis='count'),
            self._kpi(scope, 'portal_draft', 'Portal drafts', portal_draft, False, 'portal_attendance', suffix='', basis='count'),
            self._kpi(scope, 'portal_absent', 'Portal absent entries', portal_absent, False, 'portal_attendance', suffix='', basis='count'),
            self._kpi(scope, 'portal_failed', 'Portal sync failures', portal_failed, False, 'portal_sync_failures_period', suffix='', basis='count'),
            self._kpi(scope, 'conflicts', 'Work-entry conflicts', we_conflict, False, 'work_entry_conflicts', suffix='', basis='count'),
            self._kpi(scope, 'we_draft', 'Draft work entries', we_draft, False, 'draft_work_entries', suffix='', basis='count'),
            self._kpi(scope, 'we_validated', 'Validated work entries', we_validated, False, 'validated_work_entries', suffix='', basis='count'),
        ]
        charts = {}
        if self._can_read('hr.attendance') and self._field_path_exists('hr.attendance', 'employee_id.department_id'):
            charts['departments'] = self._group_chart('hr.attendance', domain, 'employee_id.department_id', 'Attendance by department')
        if self._can_read('hr.attendance') and self._field_path_exists('hr.attendance', 'employee_id.project_id'):
            charts['projects'] = self._group_chart('hr.attendance', domain, 'employee_id.project_id', 'Attendance by project')
        charts['hours'] = self._chart('area', 'Worked hours this period', ['Worked', 'Overtime'], [
            {'label': 'Hours', 'data': [round(hours or 0.0, 2), round(overtime or 0.0, 2)]},
        ], unit='hours')
        charts['presence'] = self._chart('bar', 'Present vs missing check-out', ['Present', 'Missing check-out'], [
            {'label': 'Count', 'data': [present, missing_out]},
        ], unit='count')
        charts['daily'] = self._attendance_daily_chart(scope)
        tables = {}
        if self._can_read('hr.attendance'):
            tables['attendance'] = self._mgmt_table('Recent attendance', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'check_in', 'label': 'Check in'}, {'key': 'check_out', 'label': 'Check out'},
            ], [{
                'employee': rec.get('employee_id')[1] if rec.get('employee_id') else '',
                'check_in': rec.get('check_in') or '',
                'check_out': rec.get('check_out') or '',
                'res_id': rec.get('id'),
                'action_key': 'attendances',
            } for rec in self._search_read('hr.attendance', domain, ['employee_id', 'check_in', 'check_out'], limit=20, order='check_in desc')], 'attendances')
            tables['missing'] = self._mgmt_table('Missing check-out', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'check_in', 'label': 'Check in'},
            ], [{
                'employee': rec.get('employee_id')[1] if rec.get('employee_id') else '',
                'check_in': rec.get('check_in') or '',
                'res_id': rec.get('id'),
                'action_key': 'missing_checkouts',
            } for rec in self._search_read('hr.attendance', domain + [('check_out', '=', False)], ['employee_id', 'check_in'], limit=20, order='check_in desc')], 'missing_checkouts')
        if self._can_read('project.portal.attendance') and self._has_field('project.portal.attendance', 'sync_state'):
            tables['sync'] = self._mgmt_table('Portal sync failures', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'date', 'label': 'Date'}, {'key': 'error', 'label': 'Error'},
            ], self._document_rows(
                'project.portal.attendance',
                pdomain + [('sync_state', '=', 'failed')],
                {'employee': 'employee_id', 'date': 'date', 'error': 'sync_error'},
                'portal_sync_failures_period', order='date desc', date_fields=('date',), scope=scope,
            ), 'portal_sync_failures_period')
        if self._can_read('hr.work.entry'):
            tables['conflicts'] = self._mgmt_table('Work-entry conflicts', [
                {'key': 'name', 'label': 'Entry'}, {'key': 'employee', 'label': 'Employee'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'hr.work.entry',
                wed + [('state', '=', 'conflict')],
                {'name': 'name', 'employee': 'employee_id', 'state': 'state'},
                'work_entry_conflicts', scope=scope,
            ), 'work_entry_conflicts')
        if self._can_read('hr.attendance') and self._has_field('hr.attendance', 'worked_hours'):
            groups = self.env['hr.attendance'].read_group(domain, ['worked_hours:sum'], ['employee_id'], lazy=False)
            ranked = sorted(groups, key=lambda item: item.get('worked_hours') or 0.0)[:15]
            tables['exceptions'] = self._mgmt_table('Lowest attendance hours', [
                {'key': 'employee', 'label': 'Employee'}, {'key': 'hours', 'label': 'Hours'},
            ], [{
                'employee': (row.get('employee_id') or [False, 'Unknown'])[1],
                'hours': round(row.get('worked_hours') or 0.0, 2),
                'res_id': (row.get('employee_id') or [False])[0],
                'res_field': 'employee_id',
                'action_key': 'attendances',
            } for row in ranked], 'attendances')
        warnings = [
            'No biometric/ZKTeco integration is active. Portal character times are not used for duration; synced hr.attendance datetimes are.',
            'Do not add portal rows to hr.attendance counts; they can represent the same event after sync.',
            'Late/early metrics require a stored calendar comparison and are marked unavailable.',
        ]
        return self._payload(
            scope, 'attendance', kpis, charts, tables,
            date_field='hr.attendance.check_in', warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['present', 'hours', 'missing_out', 'portal_failed', 'conflicts'],
                charts=[('daily', 8), ('presence', 4), ('hours', 6), ('departments', 6)],
                tables=['missing', 'attendance', 'sync', 'conflicts'],
                more=['overtime'],
            )},
        )

    def _attendance_daily_chart(self, scope, days=14):
        if not self._can_read('hr.attendance'):
            return self._chart('line', 'Daily attendance trend', [], [])
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        labels, values = [], []
        from datetime import timedelta
        for offset in range(days - 1, -1, -1):
            day = date_to - timedelta(days=offset)
            labels.append(day.strftime('%d %b'))
            domain = self._scope_domain('hr.attendance', scope)
            domain += self._datetime_date_domain('check_in', day, day)
            values.append(self._search_count('hr.attendance', domain))
        return self._chart('area', 'Daily attendance trend', labels, [{'label': 'Records', 'data': values}], unit='count', allow_toggle=True)

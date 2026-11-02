# -*- coding: utf-8 -*-
import hashlib
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ProjectPortalAttendance(models.Model):
    _name = 'project.portal.attendance'
    _description = 'Project Portal Daily Attendance Record'
    _order = 'date desc, employee_id asc'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        related='employee_id.job_id',
        store=True,
        readonly=True,
    )
    check_in = fields.Char(
        string='Check IN',
        help='Check IN time (24h HH:MM or 12h AM/PM)',
    )
    check_out = fields.Char(
        string='Check OUT',
        help='Check OUT time (24h HH:MM or 12h AM/PM)',
    )
    overtime = fields.Float(
        string='Overtime (Hours)',
        default=0.0,
    )
    work_entry_type = fields.Selection([
        ('attendance', 'Attendance'),
        ('absent', 'Absent'),
    ], string='Work Entry Type')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', required=True, index=True)
    hr_attendance_id = fields.Many2one(
        'hr.attendance',
        string='Odoo Attendance',
        copy=False,
        ondelete='set null',
        index=True,
    )

    # Audit
    last_editor_id = fields.Many2one('res.users', string='Last Editor', readonly=True, copy=False)
    last_edit_date = fields.Datetime(string='Last Edited On', readonly=True, copy=False)
    confirmed_by = fields.Many2one('res.users', string='Confirmed By', readonly=True, copy=False)
    confirmed_date = fields.Datetime(string='Confirmed On', readonly=True, copy=False)

    # Payroll / sync readiness
    sync_state = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('failed', 'Sync Failed'),
        ('n/a', 'N/A'),
    ], string='Sync Status', default='pending', copy=False, index=True)
    sync_error = fields.Char(string='Sync Error', readonly=True, copy=False)

    _sql_constraints = [
        (
            'project_date_employee_unique',
            'UNIQUE(project_id, date, employee_id)',
            'An attendance record already exists for this employee on this date!'
        )
    ]

    def get_time_input_value(self, which='in'):
        """Return HH:MM for HTML time inputs."""
        self.ensure_one()
        raw = self.check_in if which == 'in' else self.check_out
        parsed = self._ages_parse_portal_time(raw)
        return parsed.strftime('%H:%M') if parsed else ''

    def ages_category_key(self):
        self.ensure_one()
        return self.employee_id.ages_employee_category or 'staff'

    def ages_category_label(self):
        self.ensure_one()
        return {
            'labor': _('Labour'),
            'staff': _('Staff'),
            'site': _('Site'),
        }.get(self.ages_category_key(), _('Staff'))

    def ages_employee_type_label(self):
        """Department / labour type shown on the portal roster."""
        self.ensure_one()
        return self.employee_id.department_id.name or _('Unassigned')

    def write(self, vals):
        track_fields = {'check_in', 'check_out', 'overtime', 'work_entry_type', 'state'}
        if track_fields.intersection(vals.keys()) and not self.env.context.get('ages_skip_audit'):
            vals = dict(vals)
            vals.setdefault('last_editor_id', self.env.user.id)
            vals.setdefault('last_edit_date', fields.Datetime.now())
        return super().write(vals)

    @api.model
    def confirm_daily_attendance(self, project_id, date_str):
        records = self.sudo().search([
            ('project_id', '=', int(project_id)),
            ('date', '=', date_str),
        ])
        if not records:
            return {'status': 'error', 'message': _('No attendance records found for this date.')}

        unmarked = records.filtered(lambda r: not r.work_entry_type)
        if unmarked:
            return {
                'status': 'unmarked',
                'message': _(
                    'Cannot confirm: %s of %s employee(s) are still unmarked. '
                    'Please set Attendance or Absent for every employee, then try again.'
                ) % (len(unmarked), len(records)),
                'unmarked_count': len(unmarked),
                'total_count': len(records),
                'unmarked_employees': [
                    {
                        'id': r.id,
                        'employee_id': r.employee_id.id,
                        'name': r.employee_id.name,
                        'employee_type': r.ages_employee_type_label(),
                        'job': r.job_id.name or '',
                    }
                    for r in unmarked
                ],
            }

        now = fields.Datetime.now()
        records.sudo().with_context(ages_skip_audit=True).write({
            'state': 'confirmed',
            'confirmed_by': self.env.user.id,
            'confirmed_date': now,
            'last_editor_id': self.env.user.id,
            'last_edit_date': now,
            'sync_state': 'pending',
            'sync_error': False,
        })
        errors = records.sudo()._sync_records_to_odoo_backend()
        failed = records.filtered(lambda r: r.sync_state == 'failed')
        if errors or failed:
            return {
                'status': 'partial',
                'message': _('Attendance confirmed, but some records did not sync to Odoo:\n%s') % (
                    '\n'.join(errors[:8]) if errors else _('See Sync Failed badges on the portal.')
                ),
                'failed_count': len(failed),
            }
        return {'status': 'success', 'message': _('Attendance confirmed and synced to Odoo.')}

    @api.model
    def unconfirm_daily_attendance(self, project_id, date_str):
        """Internal users only — reopen a confirmed day for corrections."""
        if not self.env.user.has_group('base.group_user'):
            return {'status': 'error', 'message': _('Only internal users can unlock attendance.')}

        records = self.sudo().search([
            ('project_id', '=', int(project_id)),
            ('date', '=', date_str),
            ('state', '=', 'confirmed'),
        ])
        if not records:
            return {'status': 'error', 'message': _('No confirmed attendance found for this date.')}

        records.sudo().with_context(ages_skip_audit=True).write({
            'state': 'draft',
            'confirmed_by': False,
            'confirmed_date': False,
            'sync_state': 'pending',
            'sync_error': False,
            'last_editor_id': self.env.user.id,
            'last_edit_date': fields.Datetime.now(),
        })
        return {
            'status': 'success',
            'message': _('Attendance unlocked. You can edit and confirm again.'),
        }

    def _ages_employee_tz(self):
        self.ensure_one()
        tz_name = False
        employee = self.employee_id
        if employee:
            tz_name = employee.tz or (
                employee._get_tz() if hasattr(employee, '_get_tz') else False
            )
        tz_name = tz_name or self.env.user.tz or self.env.context.get('tz') or 'Asia/Karachi'
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.timezone('Asia/Karachi')

    def _ages_parse_portal_time(self, value):
        """Parse portal time strings like '08:00 AM', '8:00AM', '17:00'."""
        if not value or not str(value).strip():
            return False
        raw = ' '.join(str(value).strip().upper().replace('.', '').split())
        raw = raw.replace('AM', ' AM').replace('PM', ' PM')
        raw = ' '.join(raw.split())
        for fmt in ('%I:%M %p', '%I:%M%p', '%H:%M', '%H:%M:%S'):
            try:
                return datetime.strptime(raw, fmt).time()
            except ValueError:
                continue
        return False

    def _ages_local_to_utc_naive(self, day, clock_time, user_tz):
        local_dt = datetime.combine(day, clock_time)
        return user_tz.localize(local_dt).astimezone(pytz.utc).replace(tzinfo=None)

    def _ages_portal_datetimes(self):
        """Return naive-UTC (check_in, check_out) for this portal row."""
        self.ensure_one()
        user_tz = self._ages_employee_tz()
        project = self.project_id
        in_t = self._ages_parse_portal_time(self.check_in)
        out_t = self._ages_parse_portal_time(self.check_out)
        if not in_t:
            in_t = self._ages_parse_portal_time(project.portal_default_check_in) or time(8, 0, 0)
        if not out_t:
            out_t = self._ages_parse_portal_time(project.portal_default_check_out) or time(17, 0, 0)
        check_in_dt = self._ages_local_to_utc_naive(self.date, in_t, user_tz)
        check_out_dt = self._ages_local_to_utc_naive(self.date, out_t, user_tz)
        if check_out_dt <= check_in_dt:
            check_out_dt += timedelta(days=1)
        return check_in_dt, check_out_dt

    def _ages_attendance_env(self, employee):
        Attendance = self.env['hr.attendance'].sudo()
        company = employee.company_id
        if company:
            Attendance = Attendance.with_company(company)
        return Attendance.with_context(
            mail_create_nolog=True,
            mail_notrack=True,
            tracking_disable=True,
            ages_skip_work_entry=True,
        )

    def _ages_find_existing_attendance(self, Attendance, employee, check_in_dt, user_tz):
        """Return one attendance for the portal day; remove extras to avoid WE duplicates."""
        self.ensure_one()
        start_day_dt = self._ages_local_to_utc_naive(self.date, time.min, user_tz)
        end_day_dt = self._ages_local_to_utc_naive(self.date, time.max, user_tz)
        day_atts = Attendance.with_context(active_test=False).search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', start_day_dt),
            ('check_in', '<=', end_day_dt),
        ], order='id asc')

        if self.hr_attendance_id and self.hr_attendance_id.exists():
            main = self.hr_attendance_id
            extras = (day_atts | main) - main
        elif day_atts:
            main = day_atts[0]
            extras = day_atts - main
        else:
            return Attendance.browse()

        if extras:
            extras.with_context(ages_skip_work_entry=True).unlink()
        return main

    def _ages_rebuild_work_entries_for_synced(self, attendances):
        """After portal sync, rebuild work entries once per attendance (no duplicates)."""
        closed = attendances.filtered(lambda a: a.check_in and a.check_out)
        if not closed:
            return
        # Force a clean regenerate for the synced day(s)
        closed.with_context(ages_skip_work_entry=False)._create_work_entries()

    def _ages_sync_overtime(self, employee, attendance=None):
        """Write portal OT onto hr.attendance (approved) and hr.attendance.overtime.

        Approving the attendance OT is required so calendar-source contracts
        generate Overtime Hours work entries, and so attendance-source splits
        can size OT intervals from validated_overtime_hours.
        """
        self.ensure_one()
        attendance = attendance or self.hr_attendance_id
        ot_hours = float(self.overtime or 0.0)

        if attendance and attendance.exists():
            att_vals = {}
            if ot_hours > 0 and 'overtime_status' in attendance._fields:
                att_vals['overtime_status'] = 'approved'
            if 'validated_overtime_hours' in attendance._fields:
                att_vals['validated_overtime_hours'] = ot_hours
            if att_vals:
                attendance.with_context(ages_skip_work_entry=True).write(att_vals)

        if ot_hours <= 0 or 'hr.attendance.overtime' not in self.env.registry:
            return
        Overtime = self.env['hr.attendance.overtime'].sudo()
        existing_ot = Overtime.search([
            ('employee_id', '=', employee.id),
            ('date', '=', self.date),
            ('adjustment', '=', False),
        ], limit=1)
        ot_vals = {
            'employee_id': employee.id,
            'date': self.date,
            'duration': ot_hours,
            'duration_real': ot_hours,
        }
        if existing_ot:
            existing_ot.write(ot_vals)
        else:
            try:
                Overtime.create(ot_vals)
            except Exception:
                fallback = Overtime.search([
                    ('employee_id', '=', employee.id),
                    ('date', '=', self.date),
                ], limit=1)
                if fallback:
                    fallback.write({'duration': ot_hours, 'duration_real': ot_hours})
                else:
                    raise

    def _sync_records_to_odoo_backend(self):
        """Sync portal attendance to hr.attendance. Returns a list of error strings."""
        errors = []
        synced_attendances = self.env['hr.attendance']
        if 'hr.attendance' not in self.env.registry:
            _logger.error(
                "hr.attendance is not installed; cannot sync project portal attendance."
            )
            self.sudo().with_context(ages_skip_audit=True).write({
                'sync_state': 'failed',
                'sync_error': _('Attendances app is not installed on this database.'),
            })
            return [_('Attendances app is not installed on this database.')]

        for rec in self.sudo():
            employee = rec.employee_id
            if not employee:
                continue
            try:
                if rec.work_entry_type == 'absent':
                    rec._ages_unlink_day_attendance()
                    rec.with_context(ages_skip_audit=True).write({
                        'hr_attendance_id': False,
                        'sync_state': 'n/a',
                        'sync_error': False,
                    })
                    continue

                should_sync = (
                    rec.work_entry_type == 'attendance'
                    or bool((rec.check_in or '').strip() and (rec.check_out or '').strip())
                )
                if not should_sync:
                    rec.with_context(ages_skip_audit=True).write({
                        'sync_state': 'n/a',
                        'sync_error': False,
                    })
                    continue

                user_tz = rec._ages_employee_tz()
                check_in_dt, check_out_dt = rec._ages_portal_datetimes()
                Attendance = rec._ages_attendance_env(employee)
                existing_att = rec._ages_find_existing_attendance(
                    Attendance, employee, check_in_dt, user_tz,
                )
                att_vals = {
                    'employee_id': employee.id,
                    'check_in': check_in_dt,
                    'check_out': check_out_dt,
                }
                if existing_att:
                    existing_att.with_context(ages_skip_work_entry=True).write(att_vals)
                    attendance = existing_att
                else:
                    att_vals['in_mode'] = 'manual'
                    att_vals['out_mode'] = 'manual'
                    attendance = Attendance.create(att_vals)
                rec.with_context(ages_skip_audit=True).write({
                    'hr_attendance_id': attendance.id,
                    'sync_state': 'synced',
                    'sync_error': False,
                })
                rec._ages_sync_overtime(employee, attendance=attendance)
                synced_attendances |= attendance
            except Exception as exc:
                _logger.exception(
                    "Failed to sync portal attendance %s for employee %s",
                    rec.id, employee.display_name,
                )
                msg = '%s' % exc
                rec.with_context(ages_skip_audit=True).write({
                    'sync_state': 'failed',
                    'sync_error': msg[:255],
                })
                errors.append('%s: %s' % (employee.display_name, exc))

        # One clean work-entry rebuild per synced attendance day
        try:
            self._ages_rebuild_work_entries_for_synced(synced_attendances)
        except Exception:
            _logger.exception("Failed to rebuild work entries after portal sync")

        return errors

    def _ages_unlink_day_attendance(self):
        self.ensure_one()
        Attendance = self._ages_attendance_env(self.employee_id)
        user_tz = self._ages_employee_tz()
        start_day_dt = self._ages_local_to_utc_naive(self.date, time.min, user_tz)
        end_day_dt = self._ages_local_to_utc_naive(self.date, time.max, user_tz)
        to_unlink = Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', start_day_dt),
            ('check_in', '<=', end_day_dt),
        ])
        if self.hr_attendance_id:
            to_unlink |= self.hr_attendance_id
        # Also archive work entries for the day
        if to_unlink:
            period_start = min(
                datetime.combine(a.check_in.date(), time.min) for a in to_unlink if a.check_in
            )
            period_stop = max(
                datetime.combine((a.check_out or a.check_in).date(), time.max)
                for a in to_unlink if a.check_in
            )
            self.env['hr.work.entry'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('date_start', '<', period_stop),
                ('date_stop', '>', period_start),
                ('state', '!=', 'validated'),
            ]).write({'active': False, 'attendance_id': False})
            to_unlink.with_context(ages_skip_work_entry=True).unlink()

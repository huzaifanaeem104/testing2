# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from urllib.parse import quote

from odoo import fields, http, _
from odoo.http import request


class ProjectPortalController(http.Controller):

    # ── helpers ──────────────────────────────────────────────────────────

    def _is_internal_user(self, user=None):
        user = user or request.env.user
        return bool(user and user.has_group('base.group_user'))

    def _get_user_assigned_project(self, user):
        if not user or user._is_public():
            return False
        if 'portal_project_id' in user._fields and user.portal_project_id:
            return user.portal_project_id.sudo()
        emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if emp and 'project_id' in emp._fields and emp.project_id:
            return emp.project_id
        return False

    def _remember_recent_project(self, project_id):
        recent = list(request.session.get('ages_portal_recent_projects') or [])
        pid = int(project_id)
        if pid in recent:
            recent.remove(pid)
        recent.insert(0, pid)
        request.session['ages_portal_recent_projects'] = recent[:8]

    def _check_portal_session(self, project_id=None):
        user = request.env.user
        if not user or user._is_public():
            return False

        assigned = self._get_user_assigned_project(user)
        is_internal = self._is_internal_user(user)

        if not is_internal:
            if assigned:
                request.session['project_portal_id'] = assigned.id
                self._remember_recent_project(assigned.id)
                return assigned
            return False

        if project_id:
            try:
                project = request.env['project.project'].sudo().browse(int(project_id))
                if project.exists():
                    request.session['project_portal_id'] = project.id
                    self._remember_recent_project(project.id)
                    return project
            except (ValueError, TypeError):
                pass

        session_id = request.session.get('project_portal_id')
        if session_id:
            try:
                project = request.env['project.project'].sudo().browse(int(session_id))
                if project.exists():
                    self._remember_recent_project(project.id)
                    return project
            except (ValueError, TypeError):
                pass

        if assigned:
            request.session['project_portal_id'] = assigned.id
            self._remember_recent_project(assigned.id)
            return assigned
        return False

    def _assert_record_project(self, rec, project):
        return bool(rec and rec.exists() and rec.project_id.id == project.id)

    def _portal_project_or_error(self):
        project = self._check_portal_session(request.session.get('project_portal_id'))
        if not project:
            return False, {'status': 'unauthorized', 'message': _('Session expired or no project assigned.')}
        return project, None

    def _pin_required(self, user=None):
        user = user or request.env.user
        if self._is_internal_user(user):
            return False
        if not user.portal_pin_enabled or not user.portal_pin_hash:
            return False
        return not request.session.get('ages_portal_pin_ok')

    def _ensure_pin_or_redirect(self):
        if self._pin_required():
            return request.redirect('/project/portal/pin')
        return None

    def _validate_time_str(self, value):
        """Accept HH:MM or 12h AM/PM; return normalized HH:MM or '' / False on invalid."""
        if value in (None, False):
            return ''
        raw = str(value).strip()
        if not raw:
            return ''
        Attendance = request.env['project.portal.attendance']
        parsed = Attendance._ages_parse_portal_time(raw)
        if not parsed:
            return False
        return parsed.strftime('%H:%M')

    def _day_stats(self, records):
        total = len(records)
        present = len(records.filtered(lambda r: r.work_entry_type == 'attendance'))
        absent = len(records.filtered(lambda r: r.work_entry_type == 'absent'))
        unmarked = len(records.filtered(lambda r: not r.work_entry_type))
        ot = sum(records.mapped('overtime'))
        synced = len(records.filtered(lambda r: r.sync_state == 'synced'))
        failed = len(records.filtered(lambda r: r.sync_state == 'failed'))
        return {
            'total': total,
            'present': present,
            'absent': absent,
            'unmarked': unmarked,
            'overtime': ot,
            'synced': synced,
            'failed': failed,
        }

    def _parse_portal_date(self, date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return False

    def _can_edit_date(self, target_date, is_internal=None):
        """Internal users may mark today and past days. Portal users: today only."""
        if not target_date:
            return False
        today = fields.Date.today()
        if target_date > today:
            return False
        if is_internal is None:
            is_internal = self._is_internal_user()
        if is_internal:
            return True
        return target_date == today

    def _edit_denied(self, target_date):
        if self._can_edit_date(target_date):
            return None
        if target_date and target_date > fields.Date.today():
            return {'status': 'readonly', 'message': _('Future dates cannot be marked.')}
        if self._is_internal_user():
            return {'status': 'readonly', 'message': _('This day cannot be marked.')}
        return {
            'status': 'readonly',
            'message': _('Portal users can only mark attendance for today.'),
        }

    def _record_labour_dept_id(self, rec):
        dept = rec.employee_id.department_id
        return dept.id if dept else 0

    def _available_dept_ids(self, records):
        return {self._record_labour_dept_id(rec) for rec in records}

    def _normalize_emp_type(self, emp_type, available_ids=None):
        """Accept All, or a department that is actually on this project's roster."""
        raw = (emp_type or 'all').strip().lower()
        if not raw or raw in ('all', 'labor', 'others', 'staff', 'site'):
            return 'all'
        if raw in ('none', 'unassigned', 'dept-0', 'dept_0'):
            if available_ids is None or 0 in available_ids:
                return 'dept-0'
            return 'all'
        token = raw.replace('_', '-')
        if token.startswith('dept-'):
            token = token[5:]
        if not token.isdigit():
            return 'all'
        dept_id = int(token)
        if available_ids is not None and dept_id not in available_ids:
            return 'all'
        return 'dept-%s' % dept_id

    def _filter_by_emp_type(self, records, emp_type):
        if emp_type == 'all':
            return records
        if emp_type == 'dept-0':
            return records.filtered(lambda r: not r.employee_id.department_id)
        if emp_type.startswith('dept-'):
            dept_id = int(emp_type.split('-', 1)[1])
            return records.filtered(lambda r: r.employee_id.department_id.id == dept_id)
        return records

    def _emp_type_filters(self, records):
        """Chips for All plus each labour/department type present on this roster."""
        chips = [{'key': 'all', 'label': _('All'), 'count': len(records)}]
        by_dept = {}
        unassigned = 0
        for rec in records:
            dept = rec.employee_id.department_id
            if not dept:
                unassigned += 1
                continue
            bucket = by_dept.setdefault(dept.id, {'name': dept.name, 'count': 0})
            bucket['count'] += 1
        for dept_id, info in sorted(by_dept.items(), key=lambda item: (item[1]['name'] or '').lower()):
            chips.append({
                'key': 'dept-%s' % dept_id,
                'label': info['name'],
                'count': info['count'],
            })
        if unassigned:
            chips.append({
                'key': 'dept-0',
                'label': _('Unassigned'),
                'count': unassigned,
            })
        return chips

    # ── auth / pin / logout ──────────────────────────────────────────────

    @http.route(['/project/portal/login'], type='http', auth='public', website=True, sitemap=False)
    def portal_login(self, **kw):
        user = request.env.user
        if user and not user._is_public():
            return request.redirect('/project/portal')
        return request.redirect('/web/login?redirect=/project/portal')

    @http.route(['/project/portal/pin'], type='http', auth='user', website=True, sitemap=False)
    def portal_pin(self, **kw):
        user = request.env.user
        if self._is_internal_user(user) or not user.portal_pin_enabled:
            return request.redirect('/project/portal')
        error = False
        if request.httprequest.method == 'POST':
            pin = (kw.get('pin') or '').strip()
            if user.ages_check_portal_pin(pin):
                request.session['ages_portal_pin_ok'] = True
                return request.redirect('/project/portal')
            error = _('Incorrect PIN. Try again.')
        return request.render('ages_project_portal.portal_pin_template', {
            'error': error,
            'user_name': user.name,
        })

    @http.route(['/project/portal/exit'], type='http', auth='user', website=True, sitemap=False)
    def portal_exit(self, **kw):
        """Leave portal without destroying the Odoo session (internal users)."""
        request.session.pop('project_portal_id', None)
        request.session.pop('ages_portal_pin_ok', None)
        if self._is_internal_user():
            return request.redirect('/odoo')
        return request.redirect('/project/portal/logout')

    @http.route(['/project/portal/logout'], type='http', auth='public', website=True, sitemap=False)
    def portal_logout(self, **kw):
        request.session.pop('project_portal_id', None)
        request.session.pop('project_portal_user_id', None)
        request.session.pop('project_portal_password', None)
        request.session.pop('ages_portal_pin_ok', None)
        if request.session.uid:
            request.session.logout()
        return request.redirect('/web/login')

    # ── dashboard ────────────────────────────────────────────────────────

    @http.route(['/project/portal'], type='http', auth='user', website=True, sitemap=False)
    def portal_dashboard(self, **kw):
        user = request.env.user
        if user._is_public():
            return request.redirect('/web/login?redirect=/project/portal')

        pin_redir = self._ensure_pin_or_redirect()
        if pin_redir:
            return pin_redir

        is_internal = self._is_internal_user(user)

        if is_internal and kw.get('change_project'):
            request.session.pop('project_portal_id', None)
            project = False
            if kw.get('project_id'):
                project = self._check_portal_session(kw.get('project_id'))
        else:
            project = self._check_portal_session(kw.get('project_id'))

        if not project:
            if not is_internal:
                return request.render('ages_project_portal.portal_login_template', {
                    'error': _(
                        'No project is assigned to your user. '
                        'Ask an administrator to set “Portal Project” on your user form.'
                    ),
                    'logged_in': True,
                    'is_portal_only': True,
                })

            recent_ids = request.session.get('ages_portal_recent_projects') or []
            recent = request.env['project.project'].sudo().browse([
                i for i in recent_ids
                if request.env['project.project'].sudo().browse(i).exists()
            ])
            projects = request.env['project.project'].sudo().search([], order='name asc')
            return request.render('ages_project_portal.portal_project_picker_template', {
                'user_name': user.name,
                'projects': projects,
                'recent_projects': recent,
            })

        today = fields.Date.today()
        date_str = kw.get('date')
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else today
        except ValueError:
            target_date = today

        prev_date = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
        next_date = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
        target_date_str = target_date.strftime('%Y-%m-%d')
        is_today = (target_date == today)
        is_future = target_date > today

        employees = request.env['hr.employee'].sudo().search([
            ('project_id', '=', project.id),
        ], order='name asc')

        Attendance = request.env['project.portal.attendance'].sudo()
        existing_recs = Attendance.search([
            ('project_id', '=', project.id),
            ('date', '=', target_date),
        ])
        existing_emp_ids = set(existing_recs.mapped('employee_id').ids)
        missing_emp_ids = [e.id for e in employees if e.id not in existing_emp_ids]
        if missing_emp_ids and not is_future:
            default_in = project.portal_default_check_in or '08:00'
            default_out = project.portal_default_check_out or '17:00'
            Attendance.create([{
                'project_id': project.id,
                'date': target_date,
                'employee_id': emp_id,
                'state': 'draft',
                'check_in': default_in,
                'check_out': default_out,
                'sync_state': 'pending',
            } for emp_id in missing_emp_ids])
            existing_recs = Attendance.search([
                ('project_id', '=', project.id),
                ('date', '=', target_date),
            ])

        emp_order = {e.id: i for i, e in enumerate(employees)}
        existing_recs = existing_recs.filtered(
            lambda r: r.employee_id.id in emp_order
        ).sorted(key=lambda r: emp_order.get(r.employee_id.id, 9999))

        is_confirmed = bool(existing_recs) and all(r.state == 'confirmed' for r in existing_recs)
        is_editable = self._can_edit_date(target_date, is_internal) and not is_confirmed

        filter_type = kw.get('filter', 'all')
        available_ids = self._available_dept_ids(existing_recs)
        emp_type = self._normalize_emp_type(kw.get('emp_type'), available_ids)
        typed_recs = self._filter_by_emp_type(existing_recs, emp_type)
        filtered_recs = typed_recs
        if filter_type == 'attendance':
            filtered_recs = typed_recs.filtered(lambda r: r.work_entry_type == 'attendance')
        elif filter_type == 'absent':
            filtered_recs = typed_recs.filtered(lambda r: r.work_entry_type == 'absent')
        elif filter_type == 'unmarked':
            filtered_recs = typed_recs.filtered(lambda r: not r.work_entry_type)

        stats = self._day_stats(typed_recs)
        marked_pct = int(round(((stats['total'] - stats['unmarked']) / stats['total']) * 100)) if stats['total'] else 0

        confirmed_by = False
        confirmed_date = False
        if is_confirmed and existing_recs:
            sample = existing_recs[0]
            confirmed_by = sample.confirmed_by
            confirmed_date = sample.confirmed_date

        return request.render('ages_project_portal.portal_dashboard_template', {
            'project': project,
            'user_name': user.name,
            'is_internal': is_internal,
            'target_date_str': target_date_str,
            'target_date_formatted': target_date.strftime('%d %b %Y'),
            'prev_date': prev_date,
            'next_date': next_date,
            'is_today': is_today,
            'is_confirmed': is_confirmed,
            'is_editable': is_editable,
            'filter_type': filter_type,
            'emp_type': emp_type,
            'emp_type_filters': self._emp_type_filters(existing_recs),
            'attendance_records': filtered_recs,
            'count_total': stats['total'],
            'count_attendance': stats['present'],
            'count_absent': stats['absent'],
            'count_unmarked': stats['unmarked'],
            'roster_total': len(existing_recs),
            'marked_pct': marked_pct,
            'total_overtime': stats['overtime'],
            'count_synced': stats['synced'],
            'count_sync_failed': stats['failed'],
            'confirmed_by': confirmed_by,
            'confirmed_date': confirmed_date,
            'default_check_in': project.portal_default_check_in or '08:00',
            'default_check_out': project.portal_default_check_out or '17:00',
        })

    # ── history / summary ────────────────────────────────────────────────

    @http.route(['/project/portal/history'], type='http', auth='user', website=True, sitemap=False)
    def portal_history(self, **kw):
        pin_redir = self._ensure_pin_or_redirect()
        if pin_redir:
            return pin_redir

        project = self._check_portal_session(request.session.get('project_portal_id'))
        if not project:
            return request.redirect('/project/portal')

        today = fields.Date.today()
        try:
            date_from = datetime.strptime(kw.get('from') or '', '%Y-%m-%d').date()
        except ValueError:
            date_from = today - timedelta(days=13)
        try:
            date_to = datetime.strptime(kw.get('to') or '', '%Y-%m-%d').date()
        except ValueError:
            date_to = today

        if date_from > date_to:
            date_from, date_to = date_to, date_from

        Attendance = request.env['project.portal.attendance'].sudo()
        records = Attendance.search([
            ('project_id', '=', project.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        by_date = {}
        for rec in records:
            by_date.setdefault(rec.date, Attendance.browse())
            by_date[rec.date] |= rec

        days = []
        for day in sorted(by_date.keys(), reverse=True):
            stats = self._day_stats(by_date[day])
            confirmed = all(r.state == 'confirmed' for r in by_date[day])
            days.append({
                'date': day,
                'date_str': day.strftime('%Y-%m-%d'),
                'date_fmt': day.strftime('%d %b %Y'),
                'confirmed': confirmed,
                **stats,
            })

        return request.render('ages_project_portal.portal_history_template', {
            'project': project,
            'days': days,
            'date_from': date_from.strftime('%Y-%m-%d'),
            'date_to': date_to.strftime('%Y-%m-%d'),
            'is_internal': self._is_internal_user(),
            'user_name': request.env.user.name,
        })

    @http.route(['/project/portal/summary'], type='http', auth='user', website=True, sitemap=False)
    def portal_summary(self, **kw):
        pin_redir = self._ensure_pin_or_redirect()
        if pin_redir:
            return pin_redir

        project = self._check_portal_session(request.session.get('project_portal_id'))
        if not project:
            return request.redirect('/project/portal')

        date_str = kw.get('date') or fields.Date.today().strftime('%Y-%m-%d')
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = fields.Date.today()
            date_str = target_date.strftime('%Y-%m-%d')

        records = request.env['project.portal.attendance'].sudo().search([
            ('project_id', '=', project.id),
            ('date', '=', target_date),
        ], order='employee_id')
        stats = self._day_stats(records)

        text = (
            "AGES Attendance — %s\n"
            "Date: %s\n"
            "Present: %s | Absent: %s | Unmarked: %s | Total: %s\n"
            "Overtime: %.1f hrs\n"
            "Synced: %s | Failed: %s"
        ) % (
            project.ages_portal_display_name(),
            target_date.strftime('%d %b %Y'),
            stats['present'], stats['absent'], stats['unmarked'], stats['total'],
            stats['overtime'],
            stats['synced'], stats['failed'],
        )
        wa_url = 'https://wa.me/?text=' + quote(text)

        return request.render('ages_project_portal.portal_summary_template', {
            'project': project,
            'records': records,
            'stats': stats,
            'target_date_str': date_str,
            'target_date_formatted': target_date.strftime('%d %b %Y'),
            'wa_url': wa_url,
            'share_text': text,
            'is_internal': self._is_internal_user(),
        })

    # ── JSON APIs ────────────────────────────────────────────────────────

    @http.route('/project/portal/attendance/save', type='json', auth='user', website=True)
    def save_attendance_row(self, record_id, check_in, check_out, overtime, work_entry_type):
        if self._pin_required():
            return {'status': 'unauthorized', 'message': _('PIN required.')}
        project, err = self._portal_project_or_error()
        if err:
            return err

        rec = request.env['project.portal.attendance'].sudo().browse(int(record_id))
        if not self._assert_record_project(rec, project):
            return {'status': 'error', 'message': _('Invalid record')}

        if rec.state == 'confirmed':
            return {'status': 'readonly', 'message': _('Record is locked and readonly.')}
        denied = self._edit_denied(rec.date)
        if denied:
            return denied

        cin = self._validate_time_str(check_in)
        cout = self._validate_time_str(check_out)
        if cin is False or cout is False:
            return {'status': 'error', 'message': _('Invalid time format. Use HH:MM.')}

        rec.write({
            'check_in': cin or '',
            'check_out': cout or '',
            'overtime': float(overtime or 0.0),
            'work_entry_type': work_entry_type or False,
        })
        return {'status': 'success', 'message': _('Saved'), 'record_id': rec.id}

    @http.route('/project/portal/attendance/save_all', type='json', auth='user', website=True)
    def save_all_attendance(self, date_str, rows):
        if self._pin_required():
            return {'status': 'unauthorized', 'message': _('PIN required.')}
        project, err = self._portal_project_or_error()
        if err:
            return err

        target_date = self._parse_portal_date(date_str)
        denied = self._edit_denied(target_date)
        if denied:
            return denied

        Attendance = request.env['project.portal.attendance'].sudo()
        saved = 0
        errors = []
        for row in (rows or []):
            rec = Attendance.browse(int(row.get('record_id') or 0))
            if not self._assert_record_project(rec, project):
                continue
            if rec.state == 'confirmed' or rec.date != target_date:
                continue
            cin = self._validate_time_str(row.get('check_in'))
            cout = self._validate_time_str(row.get('check_out'))
            if cin is False or cout is False:
                errors.append(rec.employee_id.name)
                continue
            rec.write({
                'check_in': cin or '',
                'check_out': cout or '',
                'overtime': float(row.get('overtime') or 0.0),
                'work_entry_type': row.get('work_entry_type') or False,
            })
            saved += 1

        if errors:
            return {
                'status': 'error',
                'message': _('Invalid time for: %s') % ', '.join(errors[:5]),
                'saved': saved,
            }
        return {
            'status': 'success',
            'message': _('Saved %s employee record(s).') % saved,
            'saved': saved,
        }

    @http.route('/project/portal/attendance/confirm', type='json', auth='user', website=True)
    def confirm_attendance(self, date_str):
        if self._pin_required():
            return {'status': 'unauthorized', 'message': _('PIN required.')}
        project, err = self._portal_project_or_error()
        if err:
            return err
        target_date = self._parse_portal_date(date_str) or fields.Date.today()
        denied = self._edit_denied(target_date)
        if denied:
            return denied
        return request.env['project.portal.attendance'].sudo().confirm_daily_attendance(
            project.id, target_date.strftime('%Y-%m-%d'),
        )

    @http.route('/project/portal/attendance/unconfirm', type='json', auth='user', website=True)
    def unconfirm_attendance(self, date_str):
        if not self._is_internal_user():
            return {'status': 'error', 'message': _('Only internal users can unlock attendance.')}
        project, err = self._portal_project_or_error()
        if err:
            return err
        return request.env['project.portal.attendance'].sudo().unconfirm_daily_attendance(
            project.id, date_str,
        )

    @http.route('/project/portal/attendance/batch_update_unmarked', type='json', auth='user', website=True)
    def batch_update_unmarked(self, date_str, updates):
        if self._pin_required():
            return {'status': 'unauthorized', 'message': _('PIN required.')}
        project, err = self._portal_project_or_error()
        if err:
            return err

        target_date = self._parse_portal_date(date_str) or fields.Date.today()
        denied = self._edit_denied(target_date)
        if denied:
            return denied

        for item in updates or []:
            rec_id = item.get('record_id')
            wtype = item.get('work_entry_type')
            if rec_id and wtype:
                rec = request.env['project.portal.attendance'].sudo().browse(int(rec_id))
                if (
                    self._assert_record_project(rec, project)
                    and rec.state != 'confirmed'
                    and rec.date == target_date
                ):
                    vals = {'work_entry_type': wtype}
                    if wtype == 'absent':
                        vals.update({'check_in': '', 'check_out': ''})
                    elif wtype == 'attendance' and not (rec.check_in and rec.check_out):
                        vals['check_in'] = project.portal_default_check_in or '08:00'
                        vals['check_out'] = project.portal_default_check_out or '17:00'
                    rec.write(vals)

        return request.env['project.portal.attendance'].sudo().confirm_daily_attendance(
            project.id, target_date.strftime('%Y-%m-%d'),
        )


class ProjectPortalAccessRestriction(http.Controller):

    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def portal_my_home_redirect(self, **kw):
        user = request.env.user
        if user.has_group('base.group_portal') and not user.has_group('base.group_user'):
            return request.redirect('/project/portal')
        return request.redirect('/odoo')

# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from collections import defaultdict
from datetime import timedelta

import pytz

from odoo import fields, models
from odoo.addons.hr_work_entry_contract.models.hr_work_intervals import WorkIntervals
from odoo.addons.resource.models.utils import Intervals


def _ages_is_attendance_record(record):
    return bool(record) and getattr(record, '_name', None) == 'hr.attendance'


class AgesAttendanceIntervalPayload:
    """Interval payload built from hr.attendance.

    Regular slices → default Attendance (WORK100) work-entry type.
    Overtime slices → Overtime Hours (OVERTIME) work-entry type.
    """

    __slots__ = ('_record', 'overtime')

    def __init__(self, attendance, overtime=False):
        self._record = attendance
        self.overtime = bool(overtime)

    @property
    def _name(self):
        return 'hr.attendance'

    @property
    def id(self):
        return self._record.id

    def __bool__(self):
        return bool(self._record)

    def __len__(self):
        return len(self._record) if self._record else 0

    def __iter__(self):
        return iter(self._record)

    def __contains__(self, item):
        # Match recordset `'field' in record` used by work-entry generation
        try:
            return item in self._record
        except TypeError:
            return False

    def __getitem__(self, key):
        sliced = self._record[key]
        if isinstance(key, slice):
            return AgesAttendanceIntervalPayload(sliced, overtime=self.overtime) if sliced else sliced
        return sliced

    def __getattr__(self, name):
        return getattr(self._record, name)


class HrContract(models.Model):
    _inherit = 'hr.contract'

    work_entry_source = fields.Selection(
        selection_add=[('attendance', 'Attendances')],
        ondelete={'attendance': 'set default'},
    )

    def _get_more_vals_attendance_interval(self, interval):
        extra = super()._get_more_vals_attendance_interval(interval)
        record = interval[2]
        if _ages_is_attendance_record(record):
            # interval payload may be a multi-recordset / wrapper; keep first link
            attendance = record[:1]
            if attendance:
                extra.append(('attendance_id', attendance.id))
        return extra

    def _ages_get_payable_overtime_hours(self, attendance):
        """Hours of payable OT for one attendance (portal / validated / computed)."""
        hours = 0.0
        if attendance.overtime_status == 'refused':
            return 0.0
        if attendance.validated_overtime_hours:
            hours = attendance.validated_overtime_hours
        elif attendance.overtime_hours:
            hours = attendance.overtime_hours
        if hours > 0:
            return hours
        if 'hr.attendance.overtime' not in self.env.registry:
            return 0.0
        day = (attendance.check_in or fields.Datetime.now()).date()
        overtime = self.env['hr.attendance.overtime'].sudo().search([
            ('employee_id', '=', attendance.employee_id.id),
            ('date', '=', day),
            ('adjustment', '=', False),
        ], limit=1)
        return overtime.duration if overtime else 0.0

    def _ages_build_attendance_intervals(self, attendance, start_dt, end_dt):
        """Turn one closed attendance into timezone-local work intervals.

        Regular (scheduled) time → Attendance / WORK100.
        Time beyond the working schedule (or declared OT hours) → Overtime Hours.
        This keeps the two work entries non-overlapping so they never conflict.
        """
        calendar = attendance._get_employee_calendar()
        resource = attendance.employee_id.resource_id
        tz_name = (calendar.tz if calendar else False) or resource.tz or 'UTC'
        tz = pytz.timezone(tz_name)

        check_in_tz = attendance.check_in.astimezone(tz)
        check_out_tz = attendance.check_out.astimezone(tz)

        # Refused overtime must not create payable work entries
        if attendance.overtime_status == 'refused' and attendance.validated_overtime_hours:
            check_out_tz -= timedelta(hours=attendance.validated_overtime_hours)

        employee = attendance.employee_id
        employee_calendar = employee.resource_calendar_id
        flexible = bool(employee_calendar and employee_calendar.flexible_hours)

        if employee_calendar and not flexible:
            lunch = employee._employee_attendance_intervals(
                check_in_tz, check_out_tz, lunch=True,
            )
            leave_map = (
                calendar._leave_intervals_batch(check_in_tz, check_out_tz, None)
                if calendar else {False: WorkIntervals([])}
            )
            public_leaves = leave_map.get(False, WorkIntervals([]))
            lunch_without_leaves = lunch - public_leaves
            badge = Intervals([(check_in_tz, check_out_tz, attendance)]) - lunch_without_leaves
            schedule = WorkIntervals(list(
                employee._employee_attendance_intervals(check_in_tz, check_out_tz, lunch=False)
            ))
        else:
            badge = Intervals([(check_in_tz, check_out_tz, attendance)])
            schedule = WorkIntervals([])

        badge_wi = WorkIntervals([(start, stop, payload) for start, stop, payload in badge])
        threshold = self.company_id[:1].overtime_company_threshold or 0

        if schedule:
            regular = badge_wi & schedule
            overtime = badge_wi - schedule
            if threshold:
                overtime = WorkIntervals([
                    (start, stop, payload)
                    for start, stop, payload in overtime
                    if (stop - start).total_seconds() / 60.0 > threshold
                ])
        else:
            # Flexible / no calendar: carve declared OT hours from the end of the badge
            ot_hours = self._ages_get_payable_overtime_hours(attendance)
            total_hours = (check_out_tz - check_in_tz).total_seconds() / 3600.0
            if ot_hours > 0 and total_hours > ot_hours:
                split = check_out_tz - timedelta(hours=ot_hours)
                regular = WorkIntervals([(check_in_tz, split, attendance)])
                overtime = WorkIntervals([(split, check_out_tz, attendance)])
            else:
                regular = badge_wi
                overtime = WorkIntervals([])

        # Portal may store OT hours while checkout still ends at schedule end.
        # Append any missing OT after the last worked / scheduled moment.
        ot_hours = self._ages_get_payable_overtime_hours(attendance)
        if ot_hours > 0:
            existing_ot = sum(
                (stop - start).total_seconds() for start, stop, _ in overtime
            ) / 3600.0
            missing = ot_hours - existing_ot
            if missing > (1.0 / 60.0):
                anchor = check_out_tz
                if schedule:
                    stops = [stop for _start, stop, _payload in schedule]
                    if stops:
                        anchor = max(anchor, max(stops))
                overtime = overtime | WorkIntervals([
                    (anchor, anchor + timedelta(hours=missing), attendance),
                ])

        clipped = []
        for interval_start, interval_stop, _payload in regular:
            start = max(start_dt, interval_start)
            stop = min(end_dt, interval_stop)
            if start < stop:
                clipped.append((
                    start, stop,
                    AgesAttendanceIntervalPayload(attendance, overtime=False),
                ))
        for interval_start, interval_stop, _payload in overtime:
            start = max(start_dt, interval_start)
            stop = min(end_dt, interval_stop)
            if start < stop:
                clipped.append((
                    start, stop,
                    AgesAttendanceIntervalPayload(attendance, overtime=True),
                ))
        return clipped

    def _get_attendance_intervals(self, start_dt, end_dt):
        """
        Extend community calendar intervals with badge-based intervals when
        the contract work_entry_source is Attendances. For calendar contracts,
        approved overtime beyond the schedule is appended as extra intervals.
        """
        attendance_contracts = self.filtered(lambda c: c.work_entry_source == 'attendance')
        resource_ids = attendance_contracts.employee_id.resource_id.ids
        intervals_by_resource = defaultdict(list)

        attendances = self.env['hr.attendance']
        if attendance_contracts:
            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', 'in', attendance_contracts.employee_id.ids),
                ('check_in', '<', end_dt),
                ('check_out', '>', start_dt),
            ])

        for attendance in attendances:
            for piece in self._ages_build_attendance_intervals(attendance, start_dt, end_dt):
                if piece[0] < piece[1]:
                    intervals_by_resource[attendance.employee_id.resource_id.id].append(piece)

        result = {
            resource_id: WorkIntervals(pieces)
            for resource_id, pieces in ((rid, intervals_by_resource[rid]) for rid in resource_ids)
        }
        # Merge calendar-based contracts from community
        result.update(super()._get_attendance_intervals(start_dt, end_dt))

        calendar_contracts = self.filtered(lambda c: c.work_entry_source == 'calendar')
        if not calendar_contracts:
            return result

        return self._ages_merge_calendar_overtime(result, calendar_contracts, start_dt, end_dt)

    def _ages_merge_calendar_overtime(self, mapped_intervals, calendar_contracts, start_dt, end_dt):
        """Add approved overtime (beyond schedule / lunch) onto calendar contracts."""
        public_leaves = self.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),
            '|', ('calendar_id', '=', False),
            ('calendar_id', 'in', self.resource_calendar_id.ids),
            ('date_from', '<=', end_dt),
            ('date_to', '>=', start_dt),
        ])
        overtime_attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', calendar_contracts.employee_id.ids),
            ('check_in', '<=', end_dt),
            ('check_out', '>=', start_dt),
            ('overtime_status', '=', 'approved'),
        ])
        if not overtime_attendances:
            return mapped_intervals

        work_by_resource = {
            resource_id: WorkIntervals(list(intervals))
            for resource_id, intervals in mapped_intervals.items()
        }
        lunch_by_resource = self._get_lunch_intervals(start_dt, end_dt)
        threshold = self.company_id[:1].overtime_company_threshold or 0

        for attendance in overtime_attendances:
            resource = attendance.employee_id.resource_id
            schedule = work_by_resource.get(resource.id, WorkIntervals([]))
            tz = pytz.timezone(resource.tz or 'UTC')
            check_in_tz = attendance.check_in.astimezone(tz)
            check_out_tz = attendance.check_out.astimezone(tz)
            badge = WorkIntervals([(check_in_tz, check_out_tz, attendance)])

            contract = attendance.employee_id._get_contracts(
                attendance.check_in, attendance.check_out, states=['open', 'close'],
            )[:1]
            holiday = public_leaves.filtered(
                lambda leave, att=attendance, ctr=contract: (
                    (not leave.calendar_id or (ctr and leave.calendar_id == ctr.resource_calendar_id))
                    and leave.date_from <= att.check_out
                    and leave.date_to >= att.check_in
                )
            )
            if holiday:
                holiday_start = holiday[0].date_from.astimezone(tz)
                holiday_stop = holiday[0].date_to.astimezone(tz)
                rebuilt = []
                for start, stop, payload in schedule:
                    if start > holiday_stop or stop < holiday_start or check_in_tz > stop or check_out_tz < start:
                        rebuilt.append((start, stop, payload))
                    elif start > check_in_tz and stop < check_out_tz:
                        continue
                    else:
                        if start < check_in_tz:
                            rebuilt.append((start, check_in_tz, payload))
                        if stop > check_out_tz:
                            rebuilt.append((check_out_tz, stop, payload))
                schedule = WorkIntervals(rebuilt)

            lunch = lunch_by_resource.get(resource.id, WorkIntervals([]))
            overtime = badge - schedule - lunch
            if threshold:
                overtime = WorkIntervals([
                    (start, stop, payload)
                    for start, stop, payload in overtime
                    if (stop - start).total_seconds() / 60.0 > threshold
                ])
            work_by_resource[resource.id] = schedule | overtime

        return work_by_resource

    def _get_interval_work_entry_type(self, interval):
        self.ensure_one()
        payload = interval[2]

        # Explicit OT slice from attendance-source split
        if getattr(payload, 'overtime', False):
            return self.env.ref('hr_work_entry.overtime_work_entry_type')

        # Pure attendance contracts: regular badge time uses default type (WORK100)
        if self.work_entry_source == 'attendance':
            return super()._get_interval_work_entry_type(interval)

        overtime_type = getattr(payload, 'overtime_work_entry_type_id', False)
        if overtime_type:
            overtime_type = overtime_type[:1]
            if overtime_type:
                return overtime_type
        # Calendar contracts: intervals whose payload is hr.attendance are OT beyond schedule
        if _ages_is_attendance_record(payload):
            return self.env.ref('hr_work_entry.overtime_work_entry_type')
        return super()._get_interval_work_entry_type(interval)

    def _get_valid_leave_intervals(self, attendances, interval):
        self.ensure_one()
        badge_bits = WorkIntervals([
            (start, stop, record)
            for start, stop, record in attendances
            if start <= interval[1] and stop > interval[0] and _ages_is_attendance_record(record)
        ])
        if badge_bits:
            return list(WorkIntervals([interval]) - badge_bits)
        return super()._get_valid_leave_intervals(attendances, interval)

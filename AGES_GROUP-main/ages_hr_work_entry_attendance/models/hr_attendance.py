# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from datetime import datetime, time, timedelta

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.fields import Datetime


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _get_employee_calendar(self):
        self.ensure_one()
        contracts = self.employee_id.sudo()._get_contracts(
            self.check_in, self.check_out, states=['open', 'close'],
        )
        if contracts:
            return contracts[0].resource_calendar_id
        return super()._get_employee_calendar()

    def _ages_work_entry_day_bounds(self, day):
        return datetime.combine(day, time.min), datetime.combine(day, time.max)

    def _ages_collect_work_entry_vals(self):
        """Build work-entry values for attendances that fall in generated periods."""
        vals_list = []
        for attendance in self.filtered(lambda a: a.check_out):
            contracts = attendance.employee_id.sudo()._get_contracts(
                attendance.check_in, attendance.check_out, states=['open', 'close'],
            )
            for contract in contracts:
                gen_from = contract.date_generated_from
                gen_to = contract.date_generated_to
                if gen_from and gen_to:
                    if not (attendance.check_out >= gen_from and attendance.check_in <= gen_to):
                        continue

                start_stamp = attendance.check_in
                end_stamp = attendance.check_out
                start_day = start_stamp.date()
                end_day = end_stamp.date()

                if start_day == end_day:
                    vals_list += contract._get_work_entries_values(
                        *self._ages_work_entry_day_bounds(start_day)
                    )
                    continue

                vals_list += contract._get_work_entries_values(
                    start_stamp, datetime.combine(start_day, time.max),
                )
                cursor = start_day + timedelta(days=1)
                while cursor < end_day:
                    vals_list += contract._get_work_entries_values(
                        *self._ages_work_entry_day_bounds(cursor)
                    )
                    cursor += timedelta(days=1)
                vals_list += contract._get_work_entries_values(
                    datetime.combine(end_day, time.min), end_stamp,
                )
        return vals_list

    def _ages_archive_day_work_entries(self, period_start, period_stop):
        """Archive non-validated work entries in the period to avoid duplicates."""
        if not period_start or not period_stop or not self:
            return
        old = self.env['hr.work.entry'].sudo().search([
            ('employee_id', 'in', self.employee_id.ids),
            ('date_start', '<', period_stop),
            ('date_stop', '>', period_start),
            ('state', '!=', 'validated'),
            ('active', '=', True),
        ])
        if old:
            old.write({'active': False, 'attendance_id': False})

    def _create_work_entries(self):
        period_start = min(
            (datetime.combine(att.check_in.date(), time.min) for att in self if att.check_in),
            default=False,
        )
        period_stop = max(
            (datetime.combine(att.check_out.date(), time.max) for att in self if att.check_out),
            default=False,
        )
        if not period_start or not period_stop:
            return

        # Always clear previous draft/conflict work entries for this day first.
        # Portal confirm / re-sync can otherwise stack duplicate Attendance entries.
        self._ages_archive_day_work_entries(period_start, period_stop)

        raw_vals = self._ages_collect_work_entry_vals()
        if not raw_vals:
            return

        vals_list = [
            v for v in raw_vals
            if v.get('date_start') and v.get('date_stop')
            and v['date_start'] >= period_start and v['date_stop'] <= period_stop
        ]
        if not vals_list:
            return

        # Deduplicate identical intervals (same employee / start / stop / type)
        unique = {}
        for vals in vals_list:
            key = (
                vals.get('employee_id'),
                vals.get('date_start'),
                vals.get('date_stop'),
                vals.get('work_entry_type_id'),
            )
            unique[key] = vals
        vals_list = list(unique.values())

        new_entries = self.env['hr.work.entry'].sudo().create(vals_list)
        if not new_entries:
            return

        groups = self.env['hr.work.entry'].sudo()._read_group(
            [
                ('date_start', '<', period_stop),
                ('date_stop', '>', period_start),
                ('employee_id', 'in', self.employee_id.ids),
                ('active', '=', True),
            ],
            ['employee_id'],
            ['id:recordset'],
        )
        included = self.env['hr.work.entry']
        overlapping = self.env['hr.work.entry']
        for _employee, entries in groups:
            fresh = entries & new_entries
            previous = entries - new_entries
            outside = previous._to_intervals() - fresh._to_intervals()
            overlapping |= self.env['hr.work.entry']._from_intervals(outside)
            included |= previous - overlapping

        overlapping.sudo().write({'attendance_id': False})
        included.sudo().write({'active': False})

    @api.model_create_multi
    def create(self, vals_list):
        starts = [vals.get('check_in') for vals in vals_list if vals.get('check_in')]
        stops = [vals.get('check_out') for vals in vals_list if vals.get('check_out')]
        records = super().create(vals_list)
        if self.env.context.get('ages_skip_work_entry'):
            return records
        with self.env['hr.work.entry']._error_checking(
            start=min(starts, default=False),
            stop=max(stops, default=False),
            employee_ids=records.employee_id.ids,
        ):
            records._create_work_entries()
        return records

    def write(self, vals):
        locked = self.env['hr.work.entry'].sudo().search([
            ('attendance_id', 'in', self.ids),
            ('state', '=', 'validated'),
        ])
        if locked:
            raise UserError(_(
                "This attendance is linked to a validated work entry and cannot be modified."
            ))

        newly_closed = self.filtered(lambda a: not a.check_out) if vals.get('check_out') else self.env['hr.attendance']
        # Portal / full rewrite of an already-closed attendance should also refresh WE
        refresh_closed = self.env['hr.attendance']
        if not self.env.context.get('ages_skip_work_entry') and {'check_in', 'check_out'} & set(vals):
            refresh_closed = self.filtered(lambda a: a.check_out) - newly_closed

        result = super().write(vals)
        if self.env.context.get('ages_skip_work_entry'):
            return result

        to_refresh = newly_closed | refresh_closed
        if not to_refresh:
            return result

        skip_check = not bool({'check_in', 'check_out', 'employee_id'} & set(vals))
        start = min(self.mapped('check_in') + [Datetime.from_string(vals.get('check_in')) or datetime.max])
        stop = max(self.mapped('check_out') + [Datetime.from_string(vals.get('check_out')) or datetime.min])
        with self.env['hr.work.entry']._error_checking(
            start=start,
            stop=stop,
            skip=skip_check,
            employee_ids=self.employee_id.ids,
        ):
            to_refresh._create_work_entries()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_validated_work_entries(self):
        locked = self.env['hr.work.entry'].sudo().search([
            ('attendance_id', 'in', self.ids),
            ('state', '=', 'validated'),
        ])
        if locked:
            raise UserError(_(
                "This attendance is linked to a validated work entry and cannot be deleted."
            ))

    def unlink(self):
        self.env['hr.work.entry'].sudo().search([
            ('attendance_id', 'in', self.ids),
        ]).write({'active': False})
        starts = [att.check_in for att in self if att.check_in]
        stops = [att.check_out for att in self if att.check_out]
        with self.env['hr.work.entry']._error_checking(
            start=min(starts, default=False),
            stop=max(stops, default=False),
            employee_ids=self.employee_id.ids,
        ):
            return super().unlink()

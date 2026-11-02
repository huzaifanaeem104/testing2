# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Datetime
from odoo.tools.float_utils import float_compare


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    payslip_state = fields.Selection(
        selection=[
            ('normal', 'To compute in next payslip'),
            ('done', 'Computed in current payslip'),
            ('blocked', 'To defer to next payslip'),
        ],
        string='Payslip State',
        default='normal',
        required=True,
        copy=False,
        tracking=True,
    )

    def _ages_regular_payslips(self, employees, states):
        payslips = self.env['hr.payslip'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('state', 'in', states),
        ])
        return payslips.filtered(lambda slip: getattr(slip, 'is_regular', True))

    def _ages_leave_overlaps_payslip(self, leave, payslip):
        return (
            payslip.employee_id == leave.employee_id
            and payslip.date_from <= leave.date_to.date()
            and payslip.date_to >= leave.date_from.date()
        )

    def action_validate(self, check_state=True):
        all_slips = self._ages_regular_payslips(
            self.mapped('employee_id'), ['done', 'paid', 'verify'],
        )
        closed_slips = all_slips.filtered(lambda slip: slip.state in ('done', 'paid'))
        open_slips = all_slips - closed_slips

        for leave in self:
            if not leave.holiday_status_id.ages_payroll_defer:
                continue
            hits_closed = any(self._ages_leave_overlaps_payslip(leave, slip) for slip in closed_slips)
            hits_open = any(self._ages_leave_overlaps_payslip(leave, slip) for slip in open_slips)
            if hits_closed and not hits_open:
                leave.payslip_state = 'blocked'

        result = super().action_validate(check_state=check_state)
        self.sudo()._recompute_payslips()
        return result

    def action_refuse(self):
        result = super().action_refuse()
        self.sudo()._recompute_payslips()
        return result

    def _action_user_cancel(self, reason):
        result = super()._action_user_cancel(reason)
        self.sudo()._recompute_payslips()
        return result

    def _recompute_payslips(self):
        slips = self._ages_regular_payslips(self.mapped('employee_id'), ['draft', 'verify'])
        draft = self.env['hr.payslip']
        waiting = self.env['hr.payslip']
        for leave in self:
            for slip in slips:
                if not self._ages_leave_overlaps_payslip(leave, slip):
                    continue
                if slip.state == 'draft':
                    draft |= slip
                elif slip.state == 'verify':
                    waiting |= slip
        if draft and hasattr(draft, '_compute_worked_days_line_ids'):
            draft._compute_worked_days_line_ids()
        if waiting and hasattr(waiting, 'action_refresh_from_work_entries'):
            waiting.action_refresh_from_work_entries()

    def _cancel_work_entry_conflict(self):
        deferred = self.filtered(lambda leave: leave.payslip_state == 'blocked')
        activity_xmlid = 'ages_hr_payroll_holidays.mail_activity_data_hr_leave_to_defer'
        for leave in deferred:
            officer = leave.employee_id.company_id.deferred_time_off_manager
            leave.activity_schedule(
                activity_xmlid,
                summary=_('Validated Time Off to Defer'),
                note=_(
                    'Please create the work entry manually for %s.',
                    leave.employee_id._get_html_link(),
                ),
                user_id=(officer.id if officer else self.env.ref('base.user_admin').id),
            )
        return super(HrLeave, self - deferred)._cancel_work_entry_conflict()

    def activity_feedback(self, act_type_xmlids, user_id=None, feedback=None):
        if 'ages_hr_payroll_holidays.mail_activity_data_hr_leave_to_defer' in act_type_xmlids:
            self.write({'payslip_state': 'done'})
        return super().activity_feedback(act_type_xmlids, user_id=user_id, feedback=feedback)

    def action_report_to_next_month(self):
        for leave in self:
            if not leave.employee_id or leave.payslip_state != 'blocked':
                raise UserError(_('Only deferred employee time off can be reported to next month.'))
            month_span = (
                (leave.date_to.year - leave.date_from.year) * 12
                + leave.date_to.month - leave.date_from.month
            )
            if month_span > 1:
                raise UserError(_(
                    'Time off %s spans more than two months and cannot be deferred automatically.',
                    leave.display_name,
                ))

            attendance_entries = self.env['hr.work.entry'].search([
                ('employee_id', '=', leave.employee_id.id),
                ('company_id', '=', self.env.company.id),
                ('date_start', '>=', leave.date_from),
                ('date_stop', '<=', leave.date_to),
                ('work_entry_type_id.is_leave', '=', False),
            ])
            next_month_entries = self.env['hr.work.entry'].search([
                ('employee_id', '=', leave.employee_id.id),
                ('company_id', '=', self.env.company.id),
                ('state', '=', 'draft'),
                ('date_start', '>=', Datetime.to_datetime(leave.date_from + relativedelta(day=1, months=1))),
                ('date_stop', '<=', datetime.combine(
                    Datetime.to_datetime(leave.date_to + relativedelta(day=31, months=1)),
                    datetime.max.time(),
                )),
            ])
            if not next_month_entries:
                raise UserError(_(
                    'Next month work entries are missing or already validated for %s.',
                    leave.display_name,
                ))
            if not attendance_entries:
                raise UserError(_('No attendance work entries are linked to this time off.'))

            leave_type = leave.holiday_status_id.work_entry_type_id
            for entry in attendance_entries:
                matched = False
                for candidate in next_month_entries:
                    if candidate.work_entry_type_id.code != 'WORK100':
                        continue
                    if float_compare(candidate.duration, entry.duration, 2) == 0:
                        candidate.work_entry_type_id = leave_type
                        matched = True
                        break
                if not matched:
                    raise UserError(_(
                        'Not enough attendance work entries to defer time off %s. '
                        'Please adjust work entries manually.',
                        leave.display_name,
                    ))

        self.activity_feedback(['ages_hr_payroll_holidays.mail_activity_data_hr_leave_to_defer'])

    def _check_uncovered_by_validated_payslip(self):
        if not self:
            return
        payslips = self.env['hr.payslip'].sudo().search([
            ('employee_id', 'in', self.employee_id.ids),
            ('date_from', '<=', max(self.mapped('date_to'))),
            ('date_to', '>=', min(self.mapped('date_from'))),
            ('state', 'in', ['done', 'paid']),
        ])
        for leave in self:
            if any(
                self._ages_leave_overlaps_payslip(leave, slip)
                and getattr(slip, 'is_regular', True)
                for slip in payslips
            ):
                raise UserError(_(
                    'This day is already covered by a validated payslip. '
                    'Please contact HR / Payroll to adjust.'
                ))

    def write(self, vals):
        if vals.get('active'):
            self._check_uncovered_by_validated_payslip()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_payslip(self):
        self._check_uncovered_by_validated_payslip()

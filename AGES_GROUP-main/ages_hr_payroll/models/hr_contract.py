# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime

import pytz

from odoo import api, fields, models, _
from odoo.osv import expression


class HrContract(models.Model):
    _inherit = 'hr.contract'

    schedule_pay = fields.Selection([
        ('annually', 'Annually'),
        ('semi-annually', 'Semi-annually'),
        ('quarterly', 'Quarterly'),
        ('bi-monthly', 'Bi-monthly'),
        ('monthly', 'Monthly'),
        ('semi-monthly', 'Semi-monthly'),
        ('bi-weekly', 'Bi-weekly'),
        ('weekly', 'Weekly'),
        ('daily', 'Daily'),
    ], compute='_compute_schedule_pay', store=True, readonly=False)
    wage_type = fields.Selection([
        ('monthly', 'Fixed Wage'),
        ('hourly', 'Hourly Wage'),
        ('daily', 'Daily Wage'),
    ], compute='_compute_wage_type', store=True, readonly=False)
    hourly_wage = fields.Monetary('Hourly Wage', tracking=True)
    daily_wage = fields.Monetary('Daily Wage', tracking=True)
    payslips_count = fields.Integer("# Payslips", compute='_compute_payslips_count',
                                    groups="ages_hr_payroll.group_hr_payroll_user")
    time_credit = fields.Boolean('Part Time')
    work_time_rate = fields.Float(
        string='Work time rate', default=1.0,
        help='Work time rate versus full time working schedule.')
    standard_calendar_id = fields.Many2one(
        'resource.calendar', default=lambda self: self.env.company.resource_calendar_id)
    time_credit_type_id = fields.Many2one(
        'hr.work.entry.type', string='Part Time Work Entry Type',
        domain=[('is_leave', '=', True)])

    @api.depends('structure_type_id')
    def _compute_schedule_pay(self):
        for contract in self:
            contract.schedule_pay = contract.structure_type_id.default_schedule_pay or 'monthly'

    @api.depends('structure_type_id', 'employee_id')
    def _compute_wage_type(self):
        for contract in self:
            emp_cat = getattr(contract.employee_id, 'ages_employee_category', False)
            if emp_cat in ('staff', 'site'):
                contract.wage_type = 'monthly'
            elif emp_cat == 'labor':
                contract.wage_type = 'daily'
            else:
                contract.wage_type = contract.structure_type_id.wage_type or 'monthly'

    @api.onchange('employee_id')
    def _onchange_employee_id_wage_type(self):
        if self.employee_id:
            emp_cat = getattr(self.employee_id, 'ages_employee_category', False)
            if emp_cat in ('staff', 'site'):
                self.wage_type = 'monthly'
            elif emp_cat == 'labor':
                self.wage_type = 'daily'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('employee_id'):
                emp = self.env['hr.employee'].browse(vals['employee_id'])
                emp_cat = getattr(emp, 'ages_employee_category', False)
                if emp_cat in ('staff', 'site'):
                    vals['wage_type'] = 'monthly'
                elif emp_cat == 'labor':
                    vals['wage_type'] = 'daily'
        return super().create(vals_list)

    def _compute_payslips_count(self):
        count_data = self.env['hr.payslip']._read_group(
            [('contract_id', 'in', self.ids)], ['contract_id'], ['__count'])
        mapped_counts = {contract.id: count for contract, count in count_data}
        for contract in self:
            contract.payslips_count = mapped_counts.get(contract.id, 0)

    def _get_contract_wage_field(self):
        self.ensure_one()
        if self.wage_type == 'hourly':
            return 'hourly_wage'
        elif self.wage_type == 'daily':
            return 'daily_wage'
        return super()._get_contract_wage_field()

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslips'),
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id, 'default_employee_id': self.employee_id.id},
        }

    def _get_work_hours_domain(self, date_from, date_to, domain=None, inside=True):
        if domain is None:
            domain = []
        domain = expression.AND([domain, [
            ('state', 'in', ['validated', 'draft']),
            ('contract_id', 'in', self.ids),
        ]])
        if inside:
            domain = expression.AND([domain, [
                ('date_start', '>=', date_from),
                ('date_stop', '<=', date_to),
            ]])
        else:
            domain = expression.AND([domain, [
                '|', '|',
                '&', '&',
                ('date_start', '>=', date_from),
                ('date_start', '<', date_to),
                ('date_stop', '>', date_to),
                '&', '&',
                ('date_start', '<', date_from),
                ('date_stop', '<=', date_to),
                ('date_stop', '>', date_from),
                '&',
                ('date_start', '<', date_from),
                ('date_stop', '>', date_to),
            ]])
        return domain

    def _preprocess_work_hours_data(self, work_data, date_from, date_to):
        """Hook for attendance / planning bridges."""
        return

    def get_work_hours(self, date_from, date_to, domain=None):
        assert not isinstance(date_from, datetime)
        assert not isinstance(date_to, datetime)
        date_from_dt = datetime.combine(fields.Datetime.to_datetime(date_from), datetime.min.time())
        date_to_dt = datetime.combine(fields.Datetime.to_datetime(date_to), datetime.max.time())
        work_data = defaultdict(int)
        contracts_by_tz = defaultdict(lambda: self.env['hr.contract'])
        for contract in self:
            calendar = (
                contract.resource_calendar_id
                or contract.employee_id.resource_calendar_id
                or contract.company_id.resource_calendar_id
            )
            contracts_by_tz[(contract.company_id, calendar.tz)] += contract
        for (company, _tz), contracts in contracts_by_tz.items():
            work_data_tz = contracts.with_company(company).sudo()._get_work_hours(
                date_from_dt, date_to_dt, domain=domain)
            for work_entry_type_id, hours in work_data_tz.items():
                work_data[work_entry_type_id] += hours
        return work_data

    def _get_work_hours(self, date_from, date_to, domain=None):
        assert isinstance(date_from, datetime)
        assert isinstance(date_to, datetime)
        calendars = (
            self.resource_calendar_id
            or self.employee_id.resource_calendar_id
            or self.company_id.resource_calendar_id
        )
        tzs = set(calendars.mapped('tz'))
        contract_tz_name = tzs.pop() if tzs else 'UTC'
        tz = pytz.timezone(contract_tz_name) if contract_tz_name else pytz.utc
        utc = pytz.timezone('UTC')
        date_from_tz = tz.localize(date_from).astimezone(utc).replace(tzinfo=None)
        date_to_tz = tz.localize(date_to).astimezone(utc).replace(tzinfo=None)

        work_entries = self.env['hr.work.entry']._read_group(
            self._get_work_hours_domain(date_from_tz, date_to_tz, domain=domain, inside=True),
            ['work_entry_type_id'],
            ['duration:sum'],
        )
        work_data = defaultdict(int)
        work_data.update({
            work_entry_type.id: duration_sum
            for work_entry_type, duration_sum in work_entries if work_entry_type
        })
        self._preprocess_work_hours_data(work_data, date_from, date_to)

        overlapping = self.env['hr.work.entry'].search(
            self._get_work_hours_domain(date_from_tz, date_to_tz, domain=domain, inside=False))
        for work_entry in overlapping:
            date_start = max(date_from_tz, work_entry.date_start)
            date_stop = min(date_to_tz, work_entry.date_stop)
            if date_stop > date_start:
                # duration is in hours on the work entry; prorate by interval length
                total = (work_entry.date_stop - work_entry.date_start).total_seconds() or 1.0
                partial = (date_stop - date_start).total_seconds()
                work_data[work_entry.work_entry_type_id.id] += work_entry.duration * partial / total
        return work_data

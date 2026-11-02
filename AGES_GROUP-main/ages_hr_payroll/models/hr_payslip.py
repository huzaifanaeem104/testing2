# -*- coding: utf-8 -*-
import logging
import math
from collections import defaultdict
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
from odoo.tools.float_utils import float_compare
from odoo.tools.safe_eval import safe_eval, datetime as safe_eval_datetime, dateutil as safe_eval_dateutil

_logger = logging.getLogger(__name__)


class DefaultDictPayroll(defaultdict):
    def get(self, key, default=None):
        if key not in self and default is not None:
            self[key] = default
        return self[key]


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _description = 'Pay Slip'
    _inherit = ['mail.thread.cc', 'mail.thread.main.attachment', 'mail.activity.mixin']
    _order = 'date_to desc'

    struct_id = fields.Many2one(
        'hr.payroll.structure', string='Structure',
        compute='_compute_struct_id', store=True, readonly=False, tracking=True)
    structure_code = fields.Char(related="struct_id.code")
    struct_type_id = fields.Many2one('hr.payroll.structure.type', related='struct_id.type_id')
    wage_type = fields.Selection(related='contract_id.wage_type')
    name = fields.Char(
        string='Payslip Name', required=True, compute='_compute_name',
        store=True, readonly=False, default='/')
    number = fields.Char(string='Reference', copy=False)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    job_id = fields.Many2one(related='employee_id.job_id', store=True)
    date_from = fields.Date(string='From', required=True, tracking=True,
                            compute="_compute_date_from", store=True, readonly=False)
    date_to = fields.Date(string='To', required=True, tracking=True,
                          compute="_compute_date_to", store=True, readonly=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('paid', 'Paid'),
        ('cancel', 'Canceled'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft', tracking=True)
    line_ids = fields.One2many('hr.payslip.line', 'slip_id', string='Payslip Lines', copy=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        compute='_compute_company_id', store=True, default=lambda self: self.env.company)
    country_id = fields.Many2one(related='company_id.country_id', store=True)
    country_code = fields.Char(related='country_id.code')
    worked_days_line_ids = fields.One2many(
        'hr.payslip.worked_days', 'payslip_id', string='Payslip Worked Days', copy=True,
        compute='_compute_worked_days_line_ids', store=True, readonly=False)
    input_line_ids = fields.One2many(
        'hr.payslip.input', 'payslip_id', string='Payslip Inputs',
        compute='_compute_input_line_ids', store=True, readonly=False)
    paid = fields.Boolean(string='Made Payment Order?', copy=False)
    paid_date = fields.Date(string="Close Date")
    note = fields.Text(string='Internal Note')
    contract_domain_ids = fields.Many2many('hr.contract', compute='_compute_contract_domain_ids')
    contract_id = fields.Many2one(
        'hr.contract', string='Contract', tracking=True,
        domain="[('id', 'in', contract_domain_ids)]",
        compute='_compute_contract_id', store=True, readonly=False)
    credit_note = fields.Boolean(string='Credit Note')
    has_refund_slip = fields.Boolean(compute='_compute_has_refund_slip')
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Batch Name', copy=False, ondelete='cascade')
    sum_worked_hours = fields.Float(compute='_compute_worked_hours', store=True)
    compute_date = fields.Date('Computed On')
    basic_wage = fields.Monetary(compute='_compute_basic_net', store=True)
    gross_wage = fields.Monetary(compute='_compute_basic_net', store=True)
    net_wage = fields.Monetary(compute='_compute_basic_net', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id')
    is_regular = fields.Boolean(compute='_compute_is_regular')
    edited = fields.Boolean()
    queued_for_pdf = fields.Boolean(default=False)
    salary_attachment_ids = fields.Many2many(
        'hr.salary.attachment', relation='hr_payslip_hr_salary_attachment_rel',
        string='Salary Attachments', compute='_compute_salary_attachment_ids',
        store=True, readonly=False)
    salary_attachment_count = fields.Integer(compute='_compute_salary_attachment_count')
    use_worked_day_lines = fields.Boolean(related="struct_id.use_worked_day_lines")
    payment_report = fields.Binary(readonly=True)
    payment_report_filename = fields.Char(readonly=True)
    payment_report_date = fields.Date(readonly=True)
    ytd_computation = fields.Boolean(related='struct_id.ytd_computation')

    def _get_schedule_period_start(self):
        schedule = self.contract_id.schedule_pay or self.contract_id.structure_type_id.default_schedule_pay
        today = date.today()
        if schedule == 'quarterly':
            current_year_quarter = math.ceil(today.month / 3)
            date_from = today.replace(day=1, month=(current_year_quarter - 1) * 3 + 1)
        elif schedule == 'semi-annually':
            is_second_half = math.floor((today.month - 1) / 6)
            date_from = today.replace(day=1, month=7) if is_second_half else today.replace(day=1, month=1)
        elif schedule == 'annually':
            date_from = today.replace(day=1, month=1)
        elif schedule == 'weekly':
            date_from = today + relativedelta(days=-today.weekday())
        elif schedule == 'bi-weekly':
            date_from = today + relativedelta(days=-today.weekday() - 7 * (int(today.strftime("%W")) % 2 == 0))
        elif schedule == 'bi-monthly':
            current_year_slice = math.ceil(today.month / 2)
            date_from = today.replace(day=1, month=(current_year_slice - 1) * 2 + 1)
        else:
            date_from = today.replace(day=1)
        if self.contract_id and date_from < self.contract_id.date_start:
            date_from = self.contract_id.date_start
        return date_from

    @api.depends('contract_id', 'struct_id')
    def _compute_date_from(self):
        for payslip in self:
            if self.env.context.get('default_date_from'):
                payslip.date_from = self.env.context.get('default_date_from')
            else:
                payslip.date_from = payslip._get_schedule_period_start()

    def _get_schedule_timedelta(self):
        self.ensure_one()
        schedule = self.contract_id.schedule_pay or self.contract_id.structure_type_id.default_schedule_pay
        mapping = {
            'quarterly': relativedelta(months=3, days=-1),
            'semi-annually': relativedelta(months=6, days=-1),
            'annually': relativedelta(years=1, days=-1),
            'weekly': relativedelta(days=6),
            'bi-weekly': relativedelta(days=13),
            'bi-monthly': relativedelta(months=2, days=-1),
            'semi-monthly': relativedelta(days=14),
            'daily': relativedelta(days=0),
        }
        return mapping.get(schedule, relativedelta(months=1, days=-1))

    @api.depends('date_from', 'contract_id', 'struct_id')
    def _compute_date_to(self):
        for payslip in self:
            if self.env.context.get('default_date_to'):
                payslip.date_to = self.env.context.get('default_date_to')
            elif payslip.date_from:
                date_to = payslip.date_from + payslip._get_schedule_timedelta()
                if payslip.contract_id.date_end and date_to > payslip.contract_id.date_end:
                    date_to = payslip.contract_id.date_end
                payslip.date_to = date_to
            else:
                payslip.date_to = False

    @api.depends('employee_id')
    def _compute_company_id(self):
        for slip in self:
            slip.company_id = slip.employee_id.company_id or self.env.company

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_contract_domain_ids(self):
        for slip in self:
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                slip.contract_domain_ids = False
                continue
            slip.contract_domain_ids = self.env['hr.contract'].search([
                ('employee_id', '=', slip.employee_id.id),
                ('company_id', '=', slip.company_id.id),
                ('state', 'in', ['open', 'close']),
                ('date_start', '<=', slip.date_to),
                '|', ('date_end', '=', False), ('date_end', '>=', slip.date_from),
            ])

    @api.depends('employee_id', 'contract_domain_ids')
    def _compute_contract_id(self):
        for slip in self:
            if slip.contract_id and slip.contract_id in slip.contract_domain_ids:
                continue
            slip.contract_id = slip.contract_domain_ids[:1]

    @api.depends('contract_id')
    def _compute_struct_id(self):
        for slip in self:
            if slip.struct_id:
                continue
            slip.struct_id = slip.contract_id.structure_type_id.default_struct_id

    @api.depends('employee_id', 'struct_id', 'date_from')
    def _compute_name(self):
        for slip in self:
            if slip.struct_id and slip.struct_id.payslip_name:
                slip.name = slip.struct_id.payslip_name
            elif slip.employee_id and slip.date_from:
                slip.name = _('Salary Slip - %(employee)s - %(date)s',
                              employee=slip.employee_id.name,
                              date=slip.date_from.strftime('%B %Y'))
            else:
                slip.name = _('Salary Slip')

    @api.depends('line_ids.total', 'line_ids.code')
    def _compute_basic_net(self):
        line_values = self._get_line_values(['BASIC', 'GROSS', 'NET'])
        for payslip in self:
            payslip.basic_wage = line_values['BASIC'][payslip.id]['total']
            payslip.gross_wage = line_values['GROSS'][payslip.id]['total']
            payslip.net_wage = line_values['NET'][payslip.id]['total']

    @api.depends('worked_days_line_ids.number_of_hours')
    def _compute_worked_hours(self):
        for payslip in self:
            payslip.sum_worked_hours = sum(payslip.worked_days_line_ids.mapped('number_of_hours'))

    @api.depends('struct_id', 'struct_id.type_id.default_struct_id')
    def _compute_is_regular(self):
        for payslip in self:
            payslip.is_regular = bool(
                payslip.struct_id and payslip.struct_id.type_id.default_struct_id == payslip.struct_id)

    def _compute_has_refund_slip(self):
        for slip in self:
            slip.has_refund_slip = bool(self.search_count([
                ('credit_note', '=', True),
                ('employee_id', '=', slip.employee_id.id),
                ('date_from', '=', slip.date_from),
                ('date_to', '=', slip.date_to),
                ('number', 'like', slip.number or ''),
            ])) if slip.number else False

    @api.depends('employee_id', 'date_from', 'date_to', 'struct_id')
    def _compute_salary_attachment_ids(self):
        for slip in self:
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                slip.salary_attachment_ids = False
                continue
            attachments = self.env['hr.salary.attachment'].search([
                ('employee_ids', 'in', slip.employee_id.ids),
                ('state', '=', 'open'),
                ('date_start', '<=', slip.date_to),
                '|', ('date_end', '=', False), ('date_end', '>=', slip.date_from),
            ])
            slip.salary_attachment_ids = attachments

    def _compute_salary_attachment_count(self):
        for slip in self:
            slip.salary_attachment_count = len(slip.salary_attachment_ids)

    @api.depends('employee_id', 'struct_id', 'date_from', 'date_to', 'salary_attachment_ids')
    def _compute_input_line_ids(self):
        attachment_types = self._get_attachment_types()
        for slip in self:
            if not slip.employee_id or slip.state not in ('draft', 'verify') or slip.edited:
                continue
            lines = []
            # structure inputs
            for input_type in slip.struct_id.input_line_type_ids:
                if input_type.code in attachment_types:
                    continue
                existing = slip.input_line_ids.filtered(lambda l: l.input_type_id == input_type)
                if existing:
                    lines.append((4, existing.id))
                else:
                    lines.append((0, 0, {
                        'name': input_type.name,
                        'input_type_id': input_type.id,
                        'amount': 0.0,
                    }))
            # attachments
            for attachment in slip.salary_attachment_ids:
                input_type = attachment.other_input_type_id
                lines.append((0, 0, {
                    'name': attachment.name,
                    'input_type_id': input_type.id,
                    'amount': attachment._get_active_amount(),
                }))
            # keep manually added lines that are not attachment types
            for line in slip.input_line_ids:
                if line.input_type_id and line.input_type_id.code not in attachment_types \
                        and line.input_type_id not in slip.struct_id.input_line_type_ids:
                    lines.append((4, line.id))
            slip.update({'input_line_ids': [(5, 0, 0)] + lines})

    @api.model
    def _get_attachment_types(self):
        input_types = self.env['hr.payslip.input.type'].search([('available_in_attachments', '=', True)])
        return {input_type.code: input_type for input_type in input_types}

    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to')
    def _compute_worked_days_line_ids(self):
        if not self or self.env.context.get('salary_simulation'):
            return
        valid_slips = self.filtered(
            lambda p: p.employee_id and p.date_from and p.date_to and p.contract_id
            and p.struct_id and p.struct_id.use_worked_day_lines)
        self.update({'worked_days_line_ids': [(5, 0, 0)]})
        if not valid_slips:
            return
        generate_from = min(p.date_from for p in valid_slips) + relativedelta(days=-1)
        generate_to = max(p.date_to for p in valid_slips) + relativedelta(days=1)
        self.contract_id.generate_work_entries(generate_from, generate_to)
        for slip in valid_slips:
            if slip.edited:
                continue
            slip.update({'worked_days_line_ids': slip._get_new_worked_days_lines()})

    def _get_new_worked_days_lines(self):
        if self.struct_id.use_worked_day_lines:
            return [(0, 0, vals) for vals in self._get_worked_day_lines()]
        return []

    def _get_worked_day_lines_hours_per_day(self):
        self.ensure_one()
        calendar = (
            self.contract_id.resource_calendar_id
            or self.employee_id.resource_calendar_id
            or self.company_id.resource_calendar_id
        )
        return calendar.hours_per_day

    def _round_days(self, work_entry_type, days):
        if getattr(work_entry_type, 'round_days', 'NO') != 'NO':
            precision_rounding = 0.5 if work_entry_type.round_days == "HALF" else 1
            return float_round(
                days, precision_rounding=precision_rounding,
                rounding_method=work_entry_type.round_days_type or 'HALF-UP')
        return days

    def _get_worked_day_lines_values(self, domain=None):
        self.ensure_one()
        res = []
        hours_per_day = self._get_worked_day_lines_hours_per_day() or 8.0
        work_hours = self.contract_id.get_work_hours(self.date_from, self.date_to, domain=domain)
        work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
        biggest_work = work_hours_ordered[-1][0] if work_hours_ordered else 0
        add_days_rounding = 0
        for work_entry_type_id, hours in work_hours_ordered:
            work_entry_type = self.env['hr.work.entry.type'].browse(work_entry_type_id)
            days = round(hours / hours_per_day, 5) if hours_per_day else 0
            if work_entry_type_id == biggest_work:
                days += add_days_rounding
            day_rounded = self._round_days(work_entry_type, days)
            add_days_rounding += (days - day_rounded)
            res.append({
                'sequence': work_entry_type.sequence,
                'work_entry_type_id': work_entry_type_id,
                'number_of_days': day_rounded,
                'number_of_hours': hours,
            })
        work_entry_type = self.env['hr.work.entry.type']
        return sorted(res, key=lambda d: work_entry_type.browse(d['work_entry_type_id']).sequence)

    def _get_out_of_contract_calendar(self):
        self.ensure_one()
        if self.contract_id.time_credit:
            return self.contract_id.standard_calendar_id
        return (
            self.contract_id.resource_calendar_id
            or self.employee_id.resource_calendar_id
            or self.company_id.resource_calendar_id
        )

    def _get_worked_day_lines(self, domain=None, check_out_of_contract=True):
        self.ensure_one()
        res = self._get_worked_day_lines_values(domain=domain)
        if not check_out_of_contract:
            return res
        contract = self.contract_id
        out_days, out_hours = 0, 0
        reference_calendar = self._get_out_of_contract_calendar()
        if self.date_from < contract.date_start:
            start = fields.Datetime.to_datetime(self.date_from)
            stop = min(
                fields.Datetime.to_datetime(contract.date_start) + relativedelta(days=-1, hour=23, minute=59),
                fields.Datetime.to_datetime(self.date_to) + relativedelta(hour=23, minute=59))
            out_time = reference_calendar.get_work_duration_data(
                start, stop, compute_leaves=False,
                domain=['|', ('work_entry_type_id', '=', False), ('work_entry_type_id.is_leave', '=', False)])
            out_days += out_time['days']
            out_hours += out_time['hours']
        if contract.date_end and contract.date_end < self.date_to:
            start = max(
                fields.Datetime.to_datetime(contract.date_end) + relativedelta(days=1),
                fields.Datetime.to_datetime(self.date_from))
            stop = fields.Datetime.to_datetime(self.date_to) + relativedelta(hour=23, minute=59)
            out_time = reference_calendar.get_work_duration_data(
                start, stop, compute_leaves=False,
                domain=['|', ('work_entry_type_id', '=', False), ('work_entry_type_id.is_leave', '=', False)])
            out_days += out_time['days']
            out_hours += out_time['hours']
        work_entry_type = self.env.ref('ages_hr_payroll.hr_work_entry_type_out_of_contract', raise_if_not_found=False)
        if work_entry_type and (out_days or out_hours):
            res.append({
                'sequence': work_entry_type.sequence,
                'work_entry_type_id': work_entry_type.id,
                'number_of_days': out_days,
                'number_of_hours': out_hours,
            })
        return res

    def _get_regular_worked_hours(self):
        self.ensure_one()
        return sum(self.worked_days_line_ids.filtered(lambda wd: wd.is_paid).mapped('number_of_hours')) or 0.0

    @property
    def paid_amount(self):
        self.ensure_one()
        return self._get_paid_amount()

    def _get_paid_amount(self):
        self.ensure_one()
        if self.wage_type == 'hourly':
            return self.contract_id.hourly_wage * self._get_regular_worked_hours()
        return self.contract_id.contract_wage * (
            self._get_regular_worked_hours() / (self._get_regular_worked_hours() or 1.0)
        ) if self.worked_days_line_ids else self.contract_id.contract_wage

    def _is_outside_contract_dates(self):
        self.ensure_one()
        return bool(
            self.contract_id
            and (self.contract_id.date_start > self.date_to
                 or (self.contract_id.date_end and self.contract_id.date_end < self.date_from))
        )

    def _rule_parameter(self, code, reference_date=False):
        self.ensure_one()
        return self.env['hr.rule.parameter']._get_parameter_from_code(
            code, reference_date or self.date_to)

    def _sum(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute("""
            SELECT sum(pl.total)
            FROM hr_payslip as hp, hr_payslip_line as pl
            WHERE hp.employee_id = %s
            AND hp.state in ('done', 'paid')
            AND hp.date_from >= %s
            AND hp.date_to <= %s
            AND hp.id = pl.slip_id
            AND pl.code = %s""", (self.employee_id.id, from_date, to_date, code))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    def _sum_category(self, code, from_date, to_date=None):
        self.ensure_one()
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute("""
            SELECT sum(pl.total)
            FROM hr_payslip as hp, hr_payslip_line as pl,
                 hr_salary_rule_category as rc, hr_salary_rule as sr
            WHERE hp.employee_id = %s
            AND hp.state in ('done', 'paid')
            AND hp.date_from >= %s
            AND hp.date_to <= %s
            AND hp.id = pl.slip_id
            AND sr.id = pl.salary_rule_id
            AND rc.id = sr.category_id
            AND rc.code = %s""", (self.employee_id.id, from_date, to_date, code))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    def _sum_worked_days(self, code, from_date, to_date=None):
        self.ensure_one()
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute("""
            SELECT sum(hwd.amount)
            FROM hr_payslip hp, hr_payslip_worked_days hwd, hr_work_entry_type hwet
            WHERE hp.state in ('done', 'paid')
            AND hp.id = hwd.payslip_id
            AND hwet.id = hwd.work_entry_type_id
            AND hp.employee_id = %(employee)s
            AND hp.date_to <= %(stop)s
            AND hwet.code = %(code)s
            AND hp.date_from >= %(start)s""", {
            'employee': self.employee_id.id,
            'code': code,
            'start': from_date,
            'stop': to_date,
        })
        res = self.env.cr.fetchone()
        return res[0] if res else 0.0

    def _get_base_local_dict(self):
        return {
            'float_round': float_round,
            'float_compare': float_compare,
            'relativedelta': safe_eval_dateutil.relativedelta.relativedelta,
            'ceil': math.ceil,
            'floor': math.floor,
            'UserError': UserError,
            'date': safe_eval_datetime.date,
            'datetime': safe_eval_datetime.datetime,
            'defaultdict': defaultdict,
        }

    def _get_localdict(self):
        self.ensure_one()
        same_type_input_lines = defaultdict(lambda: self.env['hr.payslip.input'])
        input_line_ids_by_code = self.input_line_ids.grouped('code')
        for code, input_lines in input_line_ids_by_code.items():
            if len(input_lines) > 1:
                same_type_input_lines[code] = input_lines
        return {
            **self._get_base_local_dict(),
            'categories': DefaultDictPayroll(lambda: 0),
            'rules': DefaultDictPayroll(lambda: dict(total=0, amount=0, quantity=0)),
            'payslip': self,
            'worked_days': {line.code: line for line in self.worked_days_line_ids if line.code},
            'inputs': {line.code: line for line in self.input_line_ids if line.code},
            'employee': self.employee_id,
            'contract': self.contract_id,
            'result_rules': DefaultDictPayroll(lambda: dict(total=0, amount=0, quantity=0, rate=0)),
            'same_type_input_lines': same_type_input_lines,
        }

    def _get_rule_name(self, localdict, rule, employee_lang):
        if localdict.get('result_name'):
            return localdict['result_name']
        return rule.with_context(lang=employee_lang).name

    def _get_payslip_line_total(self, amount, quantity, rate, rule):
        self.ensure_one()
        return amount * quantity * rate / 100.0

    def _get_payslip_lines(self):
        line_vals = []
        for payslip in self:
            if not payslip.contract_id:
                raise UserError(_(
                    "There's no contract set on payslip %(payslip)s for %(employee)s.",
                    payslip=payslip.name, employee=payslip.employee_id.name))
            localdict = payslip._get_localdict()
            rules_dict = localdict['rules']
            result_rules_dict = localdict['result_rules']
            result = {}
            for rule in sorted(payslip.struct_id.rule_ids, key=lambda x: x.sequence):
                localdict.update({
                    'result': None,
                    'result_qty': 1.0,
                    'result_rate': 100,
                    'result_name': False,
                })
                if not rule._satisfy_condition(localdict):
                    continue
                employee_lang = payslip.employee_id.lang or self.env.lang
                amount, qty, rate = rule._compute_rule(localdict)
                previous_amount = localdict.get(rule.code, 0.0)
                tot_rule = payslip._get_payslip_line_total(amount, qty, rate, rule)
                localdict[rule.code] = tot_rule
                result_rules_dict[rule.code] = {
                    'total': tot_rule, 'amount': amount, 'quantity': qty, 'rate': rate}
                rules_dict[rule.code] = rule
                localdict = rule.category_id._sum_salary_rule_category(
                    localdict, tot_rule - previous_amount)
                result[rule.code] = {
                    'sequence': rule.sequence,
                    'code': rule.code,
                    'name': payslip._get_rule_name(localdict, rule, employee_lang),
                    'salary_rule_id': rule.id,
                    'contract_id': localdict['contract'].id,
                    'employee_id': localdict['employee'].id,
                    'amount': amount,
                    'quantity': qty,
                    'rate': rate,
                    'total': tot_rule,
                    'slip_id': payslip.id,
                    'ytd': tot_rule,
                }
            line_vals += list(result.values())
        return line_vals

    def _get_line_values(self, code_list, vals_list=None, compute_sum=False):
        if vals_list is None:
            vals_list = ['total']
        result = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(vals_list, 0.0)))
        if not self or not code_list:
            return result
        for payslip in self:
            for code in code_list:
                lines = payslip.line_ids.filtered(lambda l: l.code == code)
                for vals in vals_list:
                    result[code][payslip.id][vals] = sum(lines.mapped(vals))
        return result

    def compute_sheet(self):
        payslips = self.filtered(lambda slip: slip.state in ['draft', 'verify'])
        payslips.line_ids.unlink()
        self.env.flush_all()
        today = fields.Date.today()
        for payslip in payslips:
            number = payslip.number or self.env['ir.sequence'].next_by_code('salary.slip')
            payslip.write({'number': number, 'state': 'verify', 'compute_date': today})
        self.env['hr.payslip.line'].create(payslips._get_payslip_lines())
        return True

    def action_refresh_from_work_entries(self):
        if any(p.state not in ['draft', 'verify'] for p in self):
            raise UserError(_('The payslips should be in Draft or Waiting state.'))
        payslips = self.filtered(lambda p: not p.edited)
        payslips.mapped('worked_days_line_ids').unlink()
        payslips.mapped('line_ids').unlink()
        payslips._compute_worked_days_line_ids()
        payslips.compute_sheet()

    def action_payslip_draft(self):
        return self.write({'state': 'draft', 'paid_date': False})

    def action_payslip_done(self):
        invalid_payslips = self.filtered(lambda p: p._is_outside_contract_dates())
        if invalid_payslips:
            raise ValidationError(_(
                'The following employees have a contract outside of the payslip period:\n%s',
                '\n'.join(invalid_payslips.mapped('employee_id.name'))))
        if any(slip.contract_id.state == 'cancel' for slip in self):
            raise ValidationError(_('You cannot validate a payslip on which the contract is cancelled'))
        if any(slip.state == 'cancel' for slip in self):
            raise ValidationError(_("You can't validate a cancelled payslip."))
        self.write({'state': 'done'})
        self.mapped('payslip_run_id').action_close()
        regular_payslips = self.filtered(lambda p: p.is_regular)
        work_entries = self.env['hr.work.entry']
        for regular_payslip in regular_payslips:
            work_entries |= self.env['hr.work.entry'].search([
                ('date_start', '<=', regular_payslip.date_to),
                ('date_stop', '>=', regular_payslip.date_from),
                ('employee_id', '=', regular_payslip.employee_id.id),
            ])
        if work_entries:
            work_entries.action_validate()
        if self.env.context.get('payslip_generate_pdf'):
            if self.env.context.get('payslip_generate_pdf_direct'):
                self._generate_pdf()
            else:
                self.write({'queued_for_pdf': True})
                payslip_cron = self.env.ref(
                    'ages_hr_payroll.ir_cron_generate_payslip_pdfs', raise_if_not_found=False)
                if payslip_cron:
                    payslip_cron._trigger()

    def action_payslip_cancel(self):
        if (not self.env.user.has_group('ages_hr_payroll.group_hr_payroll_manager')
                and self.filtered(lambda slip: slip.state in ('done', 'paid'))):
            raise UserError(_("Cannot cancel a payslip that is done or paid."))
        self.write({'state': 'cancel', 'paid_date': False})
        self.mapped('payslip_run_id').action_close()

    def action_payslip_paid(self):
        if any(slip.state not in ['done', 'paid'] for slip in self):
            raise UserError(_('Cannot mark payslip as paid if not confirmed.'))
        self.filtered(lambda p: p.state != 'paid').write({
            'state': 'paid',
            'paid_date': fields.Date.today(),
        })

    def action_payslip_unpaid(self):
        if any(slip.state != 'paid' for slip in self):
            raise UserError(_('You cannot cancel the payment if the payslip has not been paid.'))
        self.write({'state': 'done', 'paid_date': False})

    def action_payslip_payment_report(self, export_format='csv'):
        self.ensure_one()
        return {
            'name': _('Generate a Payment Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.payment.report.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_payslip_ids': self.ids,
                'default_payslip_run_id': self.payslip_run_id.id,
                'default_export_format': export_format,
            },
        }

    def refund_sheet(self):
        copied_payslips = self.env['hr.payslip']
        for payslip in self:
            copied_payslip = payslip.copy({
                'credit_note': True,
                'name': _('Refund: %(payslip)s', payslip=payslip.name),
                'edited': True,
                'state': 'verify',
            })
            for wd in copied_payslip.worked_days_line_ids:
                wd.number_of_hours = -wd.number_of_hours
                wd.number_of_days = -wd.number_of_days
                wd.amount = -wd.amount
            for line in copied_payslip.line_ids:
                line.amount = -line.amount
                line.total = -line.total
            copied_payslips |= copied_payslip
        action = {
            'name': _("Refund Payslip"),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'target': 'current',
        }
        if len(copied_payslips) == 1:
            action.update({
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': copied_payslips.id,
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': [('id', 'in', copied_payslips.ids)],
            })
        return action

    def action_edit_payslip_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Edit Payslip Lines'),
            'res_model': 'hr.payroll.edit.payslip.lines.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payslip_id': self.id},
        }

    @api.ondelete(at_uninstall=False)
    def _unlink_if_draft_or_cancel(self):
        if any(payslip.state not in ('draft', 'cancel') for payslip in self):
            raise UserError(_('You cannot delete a payslip which is not draft or cancelled!'))

    def _generate_pdf(self):
        report = self.env.ref('ages_hr_payroll.action_report_payslip')
        for payslip in self:
            pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(report, payslip.id)
            self.env['ir.attachment'].sudo().create({
                'name': _('Payslip') + ' - %s' % (payslip.number or payslip.name),
                'type': 'binary',
                'raw': pdf_content,
                'res_model': payslip._name,
                'res_id': payslip.id,
            })

    @api.model
    def _cron_generate_pdf(self):
        slips = self.search([('queued_for_pdf', '=', True), ('state', 'in', ['done', 'paid'])], limit=50)
        slips._generate_pdf()
        slips.write({'queued_for_pdf': False})

    @api.model
    def _update_payroll_data(self):
        # Hook for dashboard/data refreshes
        return True

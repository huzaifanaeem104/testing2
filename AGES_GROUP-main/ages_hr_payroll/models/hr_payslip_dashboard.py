# -*- coding: utf-8 -*-
import random
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, format_amount
from odoo.tools.safe_eval import safe_eval, datetime as safe_eval_datetime, dateutil as safe_eval_dateutil


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    @api.model
    def _dashboard_default_action(self, name, res_model, res_ids, additional_context=None):
        additional_context = additional_context or {}
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': res_model,
            'context': {**self.env.context, **additional_context},
            'domain': [('id', 'in', res_ids)],
            'views': [[False, 'list'], [False, 'kanban'], [False, 'form']],
            'view_mode': 'list,kanban,form',
        }

    @api.model
    def get_dashboard_warnings(self):
        """Return actionable warning cards for the payroll dashboard."""
        result = []
        batch_group_read = self.env['hr.payslip.run'].with_context(lang='en_US')._read_group(
            [('date_start', '>=', fields.Date.today() - relativedelta(months=1, day=1))],
            groupby=['date_start:month'],
            order='date_start:month desc',
        )[:1]
        if batch_group_read:
            min_date = batch_group_read[-1][0] or (fields.Date.today() - relativedelta(months=1, day=1))
            last_batches = self.env['hr.payslip.run'].search([('date_start', '>=', min_date)])
        else:
            last_batches = self.env['hr.payslip.run']

        for warning in self.env['hr.payroll.dashboard.warning'].search([]):
            localdict = {
                'date': safe_eval_datetime.date,
                'datetime': safe_eval_datetime.datetime,
                'relativedelta': safe_eval_dateutil.relativedelta.relativedelta,
                'warning_count': 0,
                'warning_records': self.env['base'],
                'warning_action': False,
                'additional_context': {},
            }
            globaldict = {
                'self': self.env['hr.payslip'],
                'last_batches': last_batches,
                'defaultdict': defaultdict,
            }
            try:
                safe_eval(
                    warning.evaluation_code,
                    locals_dict=localdict,
                    globals_dict=globaldict,
                    mode='exec',
                    nocopy=True,
                )
            except Exception as exc:
                raise UserError(_(
                    "Wrong warning computation code defined for:\n"
                    "- Warning: %(warning)s\n- Error: %(error)s",
                    warning=warning.name,
                    error=exc,
                )) from exc
            if localdict['warning_count']:
                records = localdict['warning_records']
                result.append({
                    'string': warning.name,
                    'color': warning.color,
                    'count': localdict['warning_count'],
                    'action': localdict['warning_action'] or self._dashboard_default_action(
                        warning.name,
                        records._name,
                        records.ids,
                        additional_context=localdict['additional_context'],
                    ),
                })
        return result

    def _get_employee_stats_actions(self):
        result = []
        today = fields.Date.today()
        HRContract = self.env['hr.contract']
        new_contracts = HRContract.search([
            ('state', '=', 'open'),
            ('kanban_state', '=', 'normal'),
            ('date_start', '>=', today + relativedelta(months=-3, day=1)),
        ])
        past_employee_ids = {
            employee.id
            for [employee] in HRContract._read_group([
                ('employee_id', 'in', new_contracts.employee_id.ids),
                ('date_end', '<', today),
                ('state', 'in', ['open', 'close']),
                ('id', 'not in', new_contracts.ids),
            ], groupby=['employee_id'])
        }
        new_hires = new_contracts.filtered(lambda c: c.employee_id.id not in past_employee_ids)
        if new_hires:
            employees = new_hires.mapped('employee_id')
            label = _('New Employees')
            result.append({
                'string': label,
                'count': len(employees),
                'action': self._dashboard_default_action(label, 'hr.employee', employees.ids),
            })
        if 'departure_date' in self.env['hr.employee']._fields:
            gone_employees = self.env['hr.employee'].with_context(active_test=False).search([
                ('departure_date', '>=', today + relativedelta(months=-1, day=1)),
                ('company_id', 'in', self.env.companies.ids),
            ])
            if gone_employees:
                label = _('Last Departures')
                result.append({
                    'string': label,
                    'count': len(gone_employees),
                    'action': self.with_context(active_test=False)._dashboard_default_action(
                        label, 'hr.employee', gone_employees.ids,
                    ),
                })
        return result

    @api.model
    def _get_dashboard_stat_employer_cost_codes(self):
        costs = self.env['hr.salary.rule'].search_read(
            [('appears_on_employee_cost_dashboard', '=', True)],
            fields=['code', 'name'],
        )
        return {cost['code']: cost['name'] for cost in costs}

    @api.model
    def _get_dashboard_stats_employer_cost(self):
        today = fields.Date.context_today(self)
        date_formats = {'monthly': 'MMMM y', 'yearly': 'y'}
        employer_cost = {
            'type': 'stacked_bar',
            'title': _('Employer Cost'),
            'label': _('Employer Cost'),
            'id': 'employer_cost',
            'is_sample': False,
            'actions': [],
            'data': {
                'monthly': defaultdict(lambda: [{}, {}, {}]),
                'yearly': defaultdict(lambda: [{}, {}, {}]),
            },
        }
        last_payslips = self.env['hr.payslip'].search([
            ('state', '!=', 'cancel'),
            ('date_from', '>=', fields.Date.today() + relativedelta(months=-2, day=1)),
            ('date_to', '<=', fields.Date.today() + relativedelta(day=31)),
        ])
        if not last_payslips:
            employer_cost['is_sample'] = True
        cost_codes = self._get_dashboard_stat_employer_cost_codes()
        if not cost_codes:
            cost_codes = {'NET': _('Net Salary')}
        line_values = last_payslips._get_line_values(cost_codes.keys()) if last_payslips else {}
        for slip in last_payslips:
            for code, code_desc in cost_codes.items():
                start = slip.date_from
                idx = -((today.year - start.year) * 12 + (today.month - start.month) - 2)
                if idx < 0 or idx > 2:
                    continue
                amount = employer_cost['data']['monthly'][code_desc][idx].get('value', 0.0)
                amount += line_values.get(code, {}).get(slip.id, {}).get('total', 0.0)
                employer_cost['data']['monthly'][code_desc][idx]['value'] = amount
                if not employer_cost['data']['monthly'][code_desc][idx].get('label'):
                    employer_cost['data']['monthly'][code_desc][idx]['label'] = format_date(
                        self.env, start, date_format=date_formats['monthly'],
                    )
        last_payslips_y = self.env['hr.payslip'].search([
            ('state', '!=', 'cancel'),
            ('date_from', '>=', fields.Date.today() + relativedelta(years=-2, day=1)),
            ('date_to', '<=', fields.Date.today() + relativedelta(month=12, day=31)),
        ])
        line_values = last_payslips_y._get_line_values(cost_codes.keys()) if last_payslips_y else {}
        for slip in last_payslips_y:
            for code, code_desc in cost_codes.items():
                start = slip.date_from
                idx = -(today.year - start.year - 2)
                if idx < 0 or idx > 2:
                    continue
                amount = employer_cost['data']['yearly'][code_desc][idx].get('value', 0.0)
                amount += line_values.get(code, {}).get(slip.id, {}).get('total', 0.0)
                employer_cost['data']['yearly'][code_desc][idx]['value'] = amount
                if not employer_cost['data']['yearly'][code_desc][idx].get('label'):
                    employer_cost['data']['yearly'][code_desc][idx]['label'] = format_date(
                        self.env, start, date_format=date_formats['yearly'],
                    )
        for i in range(3):
            for code_desc in cost_codes.values():
                if not employer_cost['data']['monthly'][code_desc][i]:
                    value = 0 if not employer_cost['is_sample'] else random.randint(1000, 1500)
                    employer_cost['data']['monthly'][code_desc][i] = {
                        'value': value,
                        'label': format_date(
                            self.env, today + relativedelta(months=i - 2),
                            date_format=date_formats['monthly'],
                        ),
                    }
                if not employer_cost['data']['yearly'][code_desc][i]:
                    value = 0 if not employer_cost['is_sample'] else random.randint(10000, 15000)
                    employer_cost['data']['yearly'][code_desc][i] = {
                        'value': value,
                        'label': format_date(
                            self.env, today + relativedelta(years=i - 2),
                            date_format=date_formats['yearly'],
                        ),
                    }
        for data_by_code in employer_cost['data'].values():
            for data_by_type in data_by_code.values():
                for data_dict in data_by_type:
                    value = round(data_dict.get('value', 0.0), 2)
                    data_dict['value'] = value
                    data_dict['formatted_value'] = format_amount(
                        self.env, value, self.env.company.currency_id,
                    )
        return employer_cost

    @api.model
    def _get_dashboard_stat_employee_trends(self):
        today = fields.Date.context_today(self)
        employees_trends = {
            'type': 'bar',
            'title': _('Employee Count'),
            'label': _('Employee Count'),
            'id': 'employees',
            'is_sample': False,
            'actions': self._get_employee_stats_actions(),
            'data': {
                'monthly': [{}, {}, {}],
                'yearly': [{}, {}, {}],
            },
        }
        periods = [
            (today - relativedelta(months=1, day=1), today - relativedelta(day=1, days=1), 'monthly,past'),
            (today - relativedelta(day=1), today + relativedelta(months=1, day=1, days=-1), 'monthly,present'),
            (today + relativedelta(months=1, day=1), today + relativedelta(months=2, day=1, days=-1), 'monthly,future'),
            (today - relativedelta(years=1, month=1, day=1), today - relativedelta(years=1, month=12, day=31), 'yearly,past'),
            (today - relativedelta(month=1, day=1), today + relativedelta(month=12, day=31), 'yearly,present'),
            (today + relativedelta(years=1, month=1, day=1), today + relativedelta(years=1, month=12, day=31), 'yearly,future'),
        ]
        periods_sql = ', '.join(
            "(DATE '%s', DATE '%s', '%s')" % (p[0], p[1], p[2]) for p in periods
        )
        self.env.cr.execute("""
            WITH periods AS (
                SELECT * FROM (VALUES %s) x(start, _end, _type)
            )
            SELECT p.start, p._end, p._type, COUNT(DISTINCT c.employee_id) AS employee_count
              FROM periods p
              JOIN hr_contract c
                ON (c.date_end >= p.start OR c.date_end IS NULL)
               AND c.date_start <= p._end
               AND (c.state IN ('open', 'close')
                    OR (c.state = 'done' AND c.kanban_state = 'normal'))
               AND c.employee_id IS NOT NULL
               AND c.active = TRUE
               AND c.company_id IN %%s
          GROUP BY p.start, p._end, p._type
        """ % periods_sql, (tuple(self.env.companies.ids),))
        period_indexes = {'past': 0, 'present': 1, 'future': 2}
        date_formats = {'monthly': 'MMMM y', 'yearly': 'y'}
        for res in self.env.cr.dictfetchall():
            period_type, timing = res['_type'].split(',')
            period_str = format_date(self.env, res['start'], date_format=date_formats[period_type])
            employees_trends['data'][period_type][period_indexes[timing]] = {
                'label': period_str,
                'value': res['employee_count'],
                'name': period_str,
                'type': timing,
            }
        if all(not data for data in employees_trends['data']['monthly']):
            employees_trends['is_sample'] = True
        for start, _end, p_types in periods:
            period_type, timing = p_types.split(',')
            idx = period_indexes[timing]
            if not employees_trends['data'][period_type][idx]:
                period_str = format_date(self.env, start, date_format=date_formats[period_type])
                value = random.randint(1, 5) if employees_trends['is_sample'] else 0
                employees_trends['data'][period_type][idx] = {
                    'label': period_str,
                    'value': value,
                    'name': period_str,
                    'type': timing,
                }
        return employees_trends

    @api.model
    def _get_dashboard_stats(self):
        return [
            self._get_dashboard_stats_employer_cost(),
            self._get_dashboard_stat_employee_trends(),
        ]

    @api.model
    def _get_dashboard_default_sections(self):
        return ['batches', 'stats']

    @api.model
    def _get_dashboard_batch_fields(self):
        return ['id', 'date_start', 'name', 'state', 'payslip_count']

    @api.model
    def get_payroll_dashboard_data(self, sections=None):
        if sections is None:
            sections = self._get_dashboard_default_sections()
        result = {}
        if 'batches' in sections:
            batch_limit_date = fields.Date.today() - relativedelta(years=1, day=1)
            batch_group_read = self.env['hr.payslip.run'].with_context(lang='en_US')._read_group(
                [('date_start', '>=', batch_limit_date)],
                groupby=['date_start:month'],
                limit=20,
                order='date_start:month desc',
            )[:3]
            if batch_group_read:
                min_date = batch_group_read[-1][0] or fields.Date.today() - relativedelta(months=1, day=1)
                batches = self.env['hr.payslip.run'].search_read(
                    [('date_start', '>=', min_date)],
                    fields=self._get_dashboard_batch_fields(),
                )
            else:
                batches = []
            translated_states = dict(self.env['hr.payslip.run']._fields['state']._description_selection(self.env))
            for batch in batches:
                batch.update({
                    'name': "%s (%s)" % (
                        batch['name'],
                        format_date(self.env, batch['date_start'], date_format='MM/y'),
                    ),
                    'payslip_count': _('(%s Payslips)', batch['payslip_count']),
                    'state': translated_states.get(batch['state'], _('Unknown State')),
                })
            result['batches'] = batches
        if 'stats' in sections:
            result['stats'] = self._get_dashboard_stats()
        return result

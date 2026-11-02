# -*- coding: utf-8 -*-

import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.tools.misc import format_date


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_tax_periodicity = fields.Selection(
        [
            ('year', 'annually'),
            ('semester', 'semi-annually'),
            ('4_months', 'every 4 months'),
            ('trimester', 'quarterly'),
            ('2_months', 'every 2 months'),
            ('monthly', 'monthly'),
        ],
        string='Delay units',
        help='Periodicity',
        default='monthly',
        required=True,
    )
    account_tax_periodicity_reminder_day = fields.Integer(
        string='Start from',
        default=7,
        required=True,
    )
    account_tax_periodicity_journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'general')]",
        check_company=True,
    )

    def _get_default_misc_journal(self):
        self.ensure_one()
        return self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self),
            ('type', '=', 'general'),
        ], limit=1)

    def _get_tax_closing_journal(self):
        journals = self.env['account.journal']
        for company in self:
            journals |= (
                company.account_tax_periodicity_journal_id
                or company._get_default_misc_journal()
            )
        return journals

    def _get_tax_periodicity(self, report=None):
        self.ensure_one()
        return self.account_tax_periodicity or 'monthly'

    def _get_tax_periodicity_months_delay(self, report=None):
        self.ensure_one()
        return {
            'year': 12,
            'semester': 6,
            '4_months': 4,
            'trimester': 3,
            '2_months': 2,
            'monthly': 1,
        }.get(self._get_tax_periodicity(report), 1)

    def _get_tax_closing_period_boundaries(self, date, report=None):
        """Return (start, end) of the tax period that contains date."""
        self.ensure_one()
        date = fields.Date.to_date(date)
        period_months = self._get_tax_periodicity_months_delay(report)
        start_day, start_month = 1, 1
        aligned_date = date + relativedelta(days=-(start_day - 1))
        year = aligned_date.year
        month_offset = aligned_date.month - start_month
        period_number = (month_offset // period_months) + 1

        if date < datetime.date(date.year, start_month, start_day):
            year -= 1
            period_number = ((12 + month_offset) // period_months) + 1

        month_delta = period_number * period_months
        end_date = datetime.date(year, start_month, 1) + relativedelta(
            months=month_delta, days=start_day - 2,
        )
        start_date = datetime.date(year, start_month, 1) + relativedelta(
            months=month_delta - period_months, day=start_day,
        )
        return start_date, end_date

    def _get_tax_closing_move_description(self, periodicity, period_start, period_end):
        self.ensure_one()
        if periodicity == 'year':
            return f'{period_start.year}'
        if periodicity == 'trimester':
            return format_date(self.env, period_start, date_format='qqq yyyy')
        if periodicity == 'monthly':
            return format_date(self.env, period_start, date_format='LLLL yyyy')
        return f'{format_date(self.env, period_start)} - {format_date(self.env, period_end)}'

    def write(self, values):
        tax_fields = {'account_tax_periodicity', 'account_tax_periodicity_journal_id'}
        need_reminder_refresh = bool(tax_fields & set(values))
        res = super().write(values)
        if need_reminder_refresh:
            journals = self._get_tax_closing_journal().filtered(lambda journal: not journal.show_on_dashboard)
            if journals:
                journals.show_on_dashboard = True
            self._refresh_tax_return_reminders()
        return res

    def _tax_return_activity_type(self):
        return self.env.ref(
            'ages_custom_reports.tax_return_activity_type',
            raise_if_not_found=False,
        )

    def _refresh_tax_return_reminders(self):
        activity_type = self._tax_return_activity_type()
        if not activity_type:
            return
        for company in self:
            journal = company._get_tax_closing_journal()
            if not journal:
                continue
            existing = self.env['mail.activity'].sudo().search([
                ('res_id', '=', journal.id),
                ('res_model', '=', 'account.journal'),
                ('activity_type_id', '=', activity_type.id),
                ('active', '=', True),
            ])
            existing.action_cancel()
            company._generate_tax_return_reminder_activity()

    def _generate_tax_return_reminder_activity(self, date_in_period=None):
        self.ensure_one()
        activity_type = self._tax_return_activity_type()
        journal = self._get_tax_closing_journal()
        if not activity_type or not journal:
            return self.env['mail.activity']

        date_in_period = date_in_period or fields.Date.context_today(self)
        period_start, period_end = self._get_tax_closing_period_boundaries(date_in_period)
        periodicity = self._get_tax_periodicity()
        summary = _(
            'Tax Return: %(period)s',
            period=self._get_tax_closing_move_description(
                periodicity, period_start, period_end,
            ),
        )
        existing = journal.activity_ids.filtered(
            lambda act: act.activity_type_id == activity_type and act.summary == summary
        )
        if existing:
            return existing[:1]

        activity_user = self.env['res.users'].search([
            ('company_ids', 'in', self.ids),
            ('groups_id', 'in', self.env.ref('account.group_account_manager').ids),
        ], limit=1, order='id ASC')
        return self.env['mail.activity'].with_context(mail_activity_quick_update=True).create({
            'res_id': journal.id,
            'res_model_id': self.env['ir.model']._get_id('account.journal'),
            'activity_type_id': activity_type.id,
            'date_deadline': period_end + relativedelta(
                days=self.account_tax_periodicity_reminder_day or 0,
            ),
            'automated': True,
            'summary': summary,
            'user_id': activity_user.id or self.env.user.id,
        })

    @api.model
    def _cron_ensure_tax_return_reminders(self):
        for company in self.search([('chart_template', '!=', False)]):
            company._generate_tax_return_reminder_activity()

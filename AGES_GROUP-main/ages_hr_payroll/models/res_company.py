# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    ytd_reset_day = fields.Integer(default=1)
    ytd_reset_month = fields.Selection(
        [(str(i), str(i)) for i in range(1, 13)],
        default='1',
    )

    def get_last_ytd_reset_date(self, reference_date):
        self.ensure_one()
        month = int(self.ytd_reset_month or 1)
        day = min(self.ytd_reset_day or 1, 28)
        year = reference_date.year
        candidate = reference_date.replace(month=month, day=day)
        if candidate > reference_date:
            candidate = candidate.replace(year=year - 1)
        return candidate

    def _create_dashboard_notes(self):
        """Create the default payslip note for a new company.

        The user is still in the old company when Settings creates this one, so
        the multi-company rule on hr.payroll.note would block a normal create.
        """
        Note = self.env['hr.payroll.note'].sudo()
        for company in self:
            if Note.search_count([('company_id', '=', company.id)]):
                continue
            Note.create({
                'name': _('Note'),
                'company_id': company.id,
                'note': _(
                    "<p>Hello there,</p>"
                    "<p>This is where you and your team will manage your Payroll!</p>"
                    "<p><b>Warnings</b> highlight missing employee data and conflicts.<br/>"
                    "<b>Pay Runs</b> show recent batches.<br/>"
                    "<b>Employer Cost</b> and <b>Employee Count</b> summarize trends.</p>"
                ),
            })

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._create_dashboard_notes()
        return companies

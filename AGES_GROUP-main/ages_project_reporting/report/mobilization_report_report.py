# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .mobilization_report_engine import MobilizationReportEngine
from odoo.addons.ages_custom_reports.report.report_branding import (
    get_ages_branding_values,
    pdf_safe_warnings,
)


class ReportMobilizationReport(models.AbstractModel):
    _name = 'report.ages_project_reporting.mobilization_report'
    _description = 'Mobilization Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['mobilization.report.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.mobilization_report_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        form = form or {
            'date_to': fields.Date.context_today(self),
            'contract_state': 'all',
            'confirmed_only': True,
            'unfold_all': True,
        }
        form = dict(form, unfold_all=True)

        engine = MobilizationReportEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(
            report_data['lines'],
            unfolded_ids=[line['id'] for line in report_data['lines'] if line.get('foldable')],
        )
        company = self.env.company
        wizard_fields = self.env['mobilization.report.wizard']._fields
        state_label = dict(wizard_fields['contract_state'].selection).get(
            form.get('contract_state', 'all'), ''
        )
        return {
            'doc_ids': docids,
            'doc_model': 'mobilization.report.wizard',
            'data': form,
            'lines': flat_lines,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'contract_state_label': state_label,
            **get_ages_branding_values(),
            'report_title': 'Mobilization Report',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · State: {state_label}"
            ),
        }

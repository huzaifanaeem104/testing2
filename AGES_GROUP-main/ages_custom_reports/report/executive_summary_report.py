from odoo import models, api, fields

from .executive_summary_engine import ExecutiveSummaryEngine
from .report_branding import get_ages_branding_values, pdf_safe_warnings


class ReportExecutiveSummary(models.AbstractModel):
    _name = 'report.ages_custom_reports.executive_summary_report'
    _description = 'Executive Summary Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['executive.summary.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.executive_summary_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        form = form or {
            'date_to': fields.Date.context_today(self),
            'target_move': 'posted',
        }

        engine = ExecutiveSummaryEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])

        company = self.env.company
        target_move_label = dict(
            self.env['executive.summary.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        return {
            'doc_ids': docids,
            'doc_model': 'executive.summary.wizard',
            'data': form,
            'lines': flat_lines,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'Executive Summary',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

from odoo import models, api, fields

from .cash_flow_engine import CashFlowEngine
from .report_branding import (
    enrich_pdf_hierarchy_lines,
    get_ages_branding_values,
    pdf_safe_warnings,
)


class ReportCashFlow(models.AbstractModel):
    _name = 'report.ages_custom_reports.cash_flow_report'
    _description = 'Cash Flow Statement Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['cash.flow.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.cash_flow_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        form = form or {
            'date_to': fields.Date.context_today(self),
            'target_move': 'posted',
        }

        engine = CashFlowEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = enrich_pdf_hierarchy_lines(
            engine.flatten_lines(report_data['lines'])
        )

        company = self.env.company
        target_move_label = dict(
            self.env['cash.flow.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        return {
            'doc_ids': docids,
            'doc_model': 'cash.flow.wizard',
            'data': form,
            'lines': flat_lines,
            'tree_lines': report_data['lines'],
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'Cash Flow Statement',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

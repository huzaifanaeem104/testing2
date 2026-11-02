from odoo import models, api, fields

from .balance_sheet_engine import BalanceSheetEngine
from .report_branding import (
    enrich_pdf_hierarchy_lines,
    get_ages_branding_values,
    pdf_safe_warnings,
)


class ReportBalanceSheet(models.AbstractModel):
    _name = 'report.ages_custom_reports.balance_sheet_report'
    _description = 'Balance Sheet Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['balance.sheet.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.balance_sheet_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        form = form or {'date_to': fields.Date.context_today(self), 'target_move': 'posted'}

        engine = BalanceSheetEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = enrich_pdf_hierarchy_lines(
            engine.flatten_lines(report_data['lines'])
        )

        company = self.env.company
        target_move_label = dict(
            self.env['balance.sheet.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        return {
            'doc_ids': docids,
            'doc_model': 'balance.sheet.wizard',
            'data': form,
            'lines': flat_lines,
            'tree_lines': report_data['lines'],
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'Balance Sheet',
            'report_subtitle': (
                f"As of {report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

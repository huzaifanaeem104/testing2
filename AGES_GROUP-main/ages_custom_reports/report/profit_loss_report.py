from odoo import models, api, fields

from .profit_loss_engine import ProfitLossEngine
from .report_branding import (
    enrich_pdf_hierarchy_lines,
    get_ages_branding_values,
    pdf_safe_warnings,
)


class ReportProfitLoss(models.AbstractModel):
    _name = 'report.ages_custom_reports.profit_loss_report'
    _description = 'Profit and Loss Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['profit.loss.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.profit_loss_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        today = fields.Date.context_today(self)
        form = form or {'date_to': today, 'target_move': 'posted'}

        engine = ProfitLossEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = enrich_pdf_hierarchy_lines(
            engine.flatten_lines(report_data['lines'])
        )

        company = self.env.company
        target_move_label = dict(
            self.env['profit.loss.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        return {
            'doc_ids': docids,
            'doc_model': 'profit.loss.wizard',
            'data': form,
            'lines': flat_lines,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'Profit and Loss',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

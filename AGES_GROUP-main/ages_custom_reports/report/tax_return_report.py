from odoo import models, api, fields

from .tax_return_engine import TaxReturnEngine
from .report_branding import (
    get_ages_branding_values,
    pdf_safe_warnings,
    enrich_pdf_hierarchy_lines,
)


class ReportTaxReturn(models.AbstractModel):
    _name = 'report.ages_custom_reports.tax_return_report'
    _description = 'Tax Return Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['tax.return.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.tax_return_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        today = fields.Date.context_today(self)
        if not form:
            from dateutil.relativedelta import relativedelta
            date_from = today.replace(day=1)
            date_to = date_from + relativedelta(months=1, days=-1)
            form = {
                'date_from': date_from,
                'date_to': date_to,
                'target_move': 'posted',
                'comparison': False,
                'unfold_all': True,
            }

        form = dict(form, unfold_all=True)
        engine = TaxReturnEngine(self.env, form)
        report_data = engine.get_report_data()
        lines = enrich_pdf_hierarchy_lines(
            engine.flatten_lines(report_data['lines'])
        )

        company = self.env.company
        target_move_label = dict(
            self.env['tax.return.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        warning_messages = []
        for warning in report_data.get('warnings') or []:
            if isinstance(warning, dict):
                warning_messages.append(warning.get('message') or '')
            else:
                warning_messages.append(warning)
        return {
            'doc_ids': docids,
            'doc_model': 'tax.return.wizard',
            'data': form,
            'lines': lines,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'period_label': report_data['period_label'],
            'comparison': report_data['comparison'],
            'comparison_label': report_data['comparison_label'],
            'report_name': report_data['report_name'],
            'warnings': pdf_safe_warnings(warning_messages, data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'Tax Return',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"{report_data['report_name']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

from odoo import models, api, fields

from .general_ledger_engine import GeneralLedgerEngine
from .report_branding import (
    get_ages_branding_values,
    group_ledger_lines,
    pdf_safe_warnings,
)


class ReportGeneralLedger(models.AbstractModel):
    _name = 'report.ages_custom_reports.general_ledger_report'
    _description = 'General Ledger Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['general.ledger.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.general_ledger_wizard import _options_from_wizard
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
                'unfold_all': True,
            }

        form = dict(form, unfold_all=True)
        engine = GeneralLedgerEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        grouped_lines, grand_total = group_ledger_lines(flat_lines, header_type='account')

        company = self.env.company
        target_move_label = dict(
            self.env['general.ledger.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        return {
            'doc_ids': docids,
            'doc_model': 'general.ledger.wizard',
            'data': form,
            'lines': flat_lines,
            'grouped_lines': grouped_lines,
            'grand_total': grand_total,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'General Ledger',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

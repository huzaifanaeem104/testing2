from odoo import models, api, fields

from .trial_balance_engine import TrialBalanceEngine
from .report_branding import (
    get_ages_branding_values,
    pdf_safe_warnings,
    enrich_pdf_hierarchy_lines,
)


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.ages_custom_reports.trial_balance_report'
    _description = 'Trial Balance Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['trial.balance.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.trial_balance_wizard import _options_from_wizard
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
                'hierarchy': True,
            }

        form = dict(form, unfold_all=True)
        engine = TrialBalanceEngine(self.env, form)
        report_data = engine.get_report_data()
        lines = enrich_pdf_hierarchy_lines(
            engine.flatten_lines(report_data['lines'])
        )

        company = self.env.company
        target_move_label = dict(
            self.env['trial.balance.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        return {
            'doc_ids': docids,
            'doc_model': 'trial.balance.wizard',
            'data': form,
            'lines': lines,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'period_label': report_data['period_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            **get_ages_branding_values(),
            'report_title': 'Trial Balance',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

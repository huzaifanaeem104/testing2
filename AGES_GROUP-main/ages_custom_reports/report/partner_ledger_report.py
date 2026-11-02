from odoo import models, api, fields

from .partner_ledger_engine import PartnerLedgerEngine
from .report_branding import (
    get_ages_branding_values,
    group_ledger_lines,
    pdf_safe_warnings,
)


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.ages_custom_reports.partner_ledger_report'
    _description = 'Partner Ledger Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['partner.ledger.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.partner_ledger_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        form = form or {
            'date_to': fields.Date.context_today(self),
            'target_move': 'posted',
            'account_filters': ['receivable', 'payable'],
            'unfold_all': True,
        }
        # PDF always prints every partner's journal lines, same as Excel.
        form = dict(form, unfold_all=True)

        engine = PartnerLedgerEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        grouped_lines, grand_total = group_ledger_lines(flat_lines, header_type='partner')

        company = self.env.company
        target_move_label = dict(
            self.env['partner.ledger.wizard']._fields['target_move'].selection
        ).get(form.get('target_move', 'posted'), '')
        project = False
        if form.get('analytic_account_id'):
            project = self.env['account.analytic.account'].browse(
                form['analytic_account_id']
            )
        from .report_display import clip_project_name
        project_label = clip_project_name(project.display_name) if project else 'All Projects'
        return {
            'doc_ids': docids,
            'doc_model': 'partner.ledger.wizard',
            'data': form,
            'lines': flat_lines,
            'grouped_lines': grouped_lines,
            'grand_total': grand_total,
            'company': company,
            'currency': company.currency_id,
            'date_label': report_data['date_label'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'target_move_label': target_move_label,
            'project_label': project_label,
            **get_ages_branding_values(),
            'report_title': 'Partner Ledger',
            'report_subtitle': (
                f"{report_data['date_label']} · "
                f"Project: {project_label} · "
                f"Currency: {company.currency_id.name} · Target: {target_move_label}"
            ),
        }

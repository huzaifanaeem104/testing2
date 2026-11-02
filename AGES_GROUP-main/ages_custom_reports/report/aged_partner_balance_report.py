# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .aged_partner_balance_engine import AgedPartnerBalanceEngine, REPORT_TYPES
from .report_branding import get_ages_branding_values, pdf_safe_warnings


class ReportAgedPartnerBalance(models.AbstractModel):
    _name = 'report.ages_custom_reports.aged_partner_balance_report'
    _description = 'Aged Receivable and Payable PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['aged.partner.balance.wizard'].browse(docids[:1])
            if wizard.exists():
                from ..models.aged_partner_balance_wizard import _options_from_wizard
                form = _options_from_wizard(wizard)
        form = dict(form or {
            'report_type': 'receivable',
            'date_to': fields.Date.context_today(self),
            'aging_based_on': 'maturity',
            'aging_interval': 30,
            'filter_trade': True,
            'filter_non_trade': False,
        })
        form['unfold_all'] = True

        engine = AgedPartnerBalanceEngine(self.env, form)
        report_data = engine.get_report_data()
        lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        report_type = report_data['report_type']
        report_title = REPORT_TYPES[report_type]['title']
        basis_label = (
            'Invoice Date'
            if form.get('aging_based_on') == 'invoice'
            else 'Due Date'
        )
        account_scope = []
        if form.get('filter_trade', True):
            account_scope.append('Trade')
        if form.get('filter_non_trade'):
            account_scope.append('Non-Trade')
        partner_ids = form.get('partner_ids') or []
        partner_label = 'All Partners'
        if partner_ids:
            partner_label = ', '.join(
                self.env['res.partner'].browse(partner_ids).mapped('display_name')
            )

        return {
            'doc_ids': docids,
            'doc_model': 'aged.partner.balance.wizard',
            'data': form,
            'company': company,
            'currency': company.currency_id,
            'lines': lines,
            'columns': report_data['columns'],
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'date_label': report_data['date_label'],
            'basis_label': basis_label,
            'interval_label': f"{engine.aging_interval} Days",
            'partner_label': partner_label,
            'account_scope_label': ', '.join(account_scope) or 'No Accounts',
            **get_ages_branding_values(),
            'report_title': report_title,
            'report_subtitle': (
                f"As of {report_data['date_label']} · "
                f"Based on {basis_label} · "
                f"{engine.aging_interval} Day intervals · "
                f"Currency: {company.currency_id.name}"
            ),
        }

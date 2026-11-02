# -*- coding: utf-8 -*-

from odoo import api, models

from odoo.addons.ages_custom_reports.report.report_branding import (
    get_ages_branding_values,
    pdf_safe_warnings,
)

from .opal_report_engine import OpalVendorBalanceEngine
from ..models.opal_report_wizard import _options_from_wizard

TAB_TITLES = {
    'vendor_project': 'Vendor by Project',
    'vendor_account': 'By Account',
    'vendor_total': 'Vendor Totals',
    'project_total': 'Project Totals',
}


class ReportOpalVendorBalance(models.AbstractModel):
    _name = 'report.ages_opal_vendor_balance.opal_vendor_balance_report'
    _description = 'OPAL Vendor Balance PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['opal.report.wizard'].browse(docids[:1])
            if wizard.exists():
                form = _options_from_wizard(wizard)
        form = form or {'tab': 'vendor_project'}
        engine = OpalVendorBalanceEngine(self.env, form)
        report_data = engine.get_report_data()
        company = self.env.company
        tab = report_data.get('tab') or 'vendor_project'
        return {
            'doc_ids': docids,
            'doc_model': 'opal.report.wizard',
            'data': form,
            'lines': report_data['lines'],
            'columns': engine.visible_columns(report_data['columns']),
            'totals': report_data['totals'],
            'company': company,
            'currency': company.currency_id,
            'warnings': pdf_safe_warnings(report_data['warnings'], data),
            'tab_title': TAB_TITLES.get(tab, tab),
            **get_ages_branding_values(),
            'report_title': 'OPAL Vendor Balance by Project',
            'report_subtitle': (
                '%s · Reference only — OPAL static data. Does not post to Odoo ledgers. · %s'
                % (TAB_TITLES.get(tab, tab), company.currency_id.name)
            ),
        }

# -*- coding: utf-8 -*-
"""Partner Ledger OPAL enrichments — stays inside ages_opal_vendor_balance."""

from odoo.addons.ages_custom_reports.report.partner_ledger_engine import PartnerLedgerEngine

_original_get_report_data = PartnerLedgerEngine.get_report_data
_original_get_partner_detail = PartnerLedgerEngine.get_partner_detail


def _opal_hook(env):
    if 'opal.partner.ledger.hook' not in env:
        return None
    return env['opal.partner.ledger.hook']


def _patched_get_report_data(self):
    data = _original_get_report_data(self)
    hook = _opal_hook(self.env)
    if not hook or not self.options.get('show_opal_balance'):
        return data
    return hook.enrich_partner_ledger_data(self, data)


def _patched_get_partner_detail(self, partner_id):
    result = _original_get_partner_detail(self, partner_id)
    hook = _opal_hook(self.env)
    if not hook or not self.options.get('show_opal_balance'):
        return result
    partner = self.env['res.partner'].browse(partner_id) if partner_id else False
    if not partner:
        return result
    opal_children = hook.get_partner_children(partner, self.options, self.currency)
    if not opal_children:
        return result
    merged = {
        'children': list(result.get('children') or []),
    }
    hook._merge_opal_children(merged, opal_children)
    return merged


PartnerLedgerEngine.get_report_data = _patched_get_report_data
PartnerLedgerEngine.get_partner_detail = _patched_get_partner_detail

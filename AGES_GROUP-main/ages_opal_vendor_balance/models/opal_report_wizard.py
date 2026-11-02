# -*- coding: utf-8 -*-

from odoo import api, fields, models

from ..report.opal_report_engine import OpalVendorBalanceEngine


def _options_from_wizard(wizard, extra=None):
    extra = extra or {}
    options = {
        'tab': extra.get('tab') or wizard.tab or 'vendor_project',
        'as_of': extra.get('as_of') or wizard.as_of,
        'vendor_names': extra.get('vendor_names', wizard.vendor_names) or [],
        'project_codes': extra.get('project_codes', wizard.project_codes) or [],
        'account_names': extra.get('account_names', wizard.account_names) or [],
        'partner_ids': extra.get('partner_ids', wizard.partner_ids.ids) or [],
        'project_ids': extra.get('project_ids', wizard.project_ids.ids) or [],
        'sub_company_ids': extra.get('sub_company_ids', wizard.sub_company_ids.ids) or [],
        'line_search': extra.get('line_search', wizard.line_search) or '',
        'show_zero_lines': extra.get('show_zero_lines', wizard.show_zero_lines),
        'show_odoo_overall': extra.get('show_odoo_overall', wizard.show_odoo_overall),
        'show_unmapped_only': extra.get('show_unmapped_only', wizard.show_unmapped_only),
        'hidden_column_ids': extra.get('hidden_column_ids', wizard.hidden_column_ids) or [],
    }
    if extra.get('full_dataset'):
        options.update({
            'full_dataset': True,
            'vendor_names': [],
            'project_codes': [],
            'account_names': [],
            'partner_ids': [],
            'project_ids': [],
            'line_search': '',
            'show_zero_lines': True,
            'show_unmapped_only': False,
        })
    return options


class OpalReportWizard(models.TransientModel):
    _name = 'opal.report.wizard'
    _description = 'OPAL Vendor Balance Report Wizard'

    tab = fields.Selection(
        [
            ('vendor_project', 'Vendor by Project'),
            ('vendor_account', 'By Account'),
            ('vendor_total', 'Vendor Totals'),
            ('project_total', 'Project Totals'),
        ],
        default='vendor_project',
        required=True,
    )
    as_of = fields.Date(default=fields.Date.context_today, required=True)
    vendor_names = fields.Json(default=lambda self: [])
    project_codes = fields.Json(default=lambda self: [])
    account_names = fields.Json(default=lambda self: [])
    partner_ids = fields.Many2many('res.partner')
    project_ids = fields.Many2many('project.project')
    sub_company_ids = fields.Many2many('ages.sub.company')
    line_search = fields.Char()
    show_zero_lines = fields.Boolean(default=True)
    show_odoo_overall = fields.Boolean(default=False)
    show_unmapped_only = fields.Boolean(default=False)
    hidden_column_ids = fields.Json(default=lambda self: [])
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
    )

    def _get_engine(self, extra=None):
        self.ensure_one()
        return OpalVendorBalanceEngine(self.env, _options_from_wizard(self, extra))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        engine = OpalVendorBalanceEngine(wizard.env, _options_from_wizard(wizard))
        options = engine.get_filter_options()
        return {
            'tab': wizard.tab,
            'as_of': fields.Date.to_string(wizard.as_of) if wizard.as_of else False,
            'vendor_names': wizard.vendor_names or [],
            'project_codes': wizard.project_codes or [],
            'account_names': wizard.account_names or [],
            'partner_ids': wizard.partner_ids.ids,
            'project_ids': wizard.project_ids.ids,
            'sub_company_ids': wizard.sub_company_ids.ids,
            'sub_company_names': wizard.sub_company_ids.mapped('display_name'),
            'line_search': wizard.line_search or '',
            'show_zero_lines': wizard.show_zero_lines,
            'show_odoo_overall': wizard.show_odoo_overall,
            'show_unmapped_only': wizard.show_unmapped_only,
            'hidden_column_ids': wizard.hidden_column_ids or [],
            **options,
        }

    @api.model
    def update_filters(self, wizard_id, filters):
        wizard = self.browse(wizard_id)
        vals = {}
        mapping = {
            'tab': 'tab',
            'as_of': 'as_of',
            'vendor_names': 'vendor_names',
            'project_codes': 'project_codes',
            'account_names': 'account_names',
            'line_search': 'line_search',
            'show_zero_lines': 'show_zero_lines',
            'show_odoo_overall': 'show_odoo_overall',
            'show_unmapped_only': 'show_unmapped_only',
            'hidden_column_ids': 'hidden_column_ids',
        }
        for key, field in mapping.items():
            if key in filters:
                vals[field] = filters[key]
        if 'partner_ids' in filters:
            vals['partner_ids'] = [(6, 0, filters['partner_ids'] or [])]
        if 'project_ids' in filters:
            vals['project_ids'] = [(6, 0, filters['project_ids'] or [])]
        if 'sub_company_ids' in filters:
            vals['sub_company_ids'] = [(6, 0, filters['sub_company_ids'] or [])]
        wizard.write(vals)
        return wizard.get_filter_values(wizard.id)

    @api.model
    def get_report_data(self, wizard_id, extra=None):
        wizard = self.browse(wizard_id)
        return wizard._get_engine(extra).get_report_data()

    def _get_report_data(self):
        self.ensure_one()
        return {
            'ids': self.ids,
            'model': self._name,
            'form': _options_from_wizard(self),
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            'ages_opal_vendor_balance.action_report_opal_vendor_balance_pdf'
        ).report_action(self, data=self._get_report_data())

    def action_print_excel(self):
        self.ensure_one()
        return self.env.ref(
            'ages_opal_vendor_balance.action_report_opal_vendor_balance_xlsx'
        ).report_action(self, data=self._get_report_data())

    @api.model
    def action_open_partner(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': partner.display_name,
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def action_open_partner_ledger(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return False
        ledger = self.env['partner.ledger.wizard'].create({
            'partner_ids': [(6, 0, [partner.id])],
            'filter_payable': True,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'ages_partner_ledger_report',
            'name': partner.display_name,
            'params': {'wizard_id': ledger.id},
        }

    @api.model
    def action_open_project(self, project_id):
        project = self.env['project.project'].browse(project_id)
        if not project.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': project.display_name,
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def action_open_vendor_mapping(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'OPAL Vendor Mapping',
            'res_model': 'opal.vendor.map',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'target': 'current',
            'context': {'search_default_unmapped': 1},
        }

    @api.model
    def action_open_import_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import OPAL Excel',
            'res_model': 'opal.import.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

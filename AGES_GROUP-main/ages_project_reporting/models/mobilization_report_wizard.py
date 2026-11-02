# -*- coding: utf-8 -*-

from odoo import api, fields, models

from odoo.addons.ages_custom_reports.report.report_display import clip_project_name


def _default_fiscal_dates(wizard):
    today = fields.Date.context_today(wizard)
    fy = wizard.env.company.compute_fiscalyear_dates(today)
    return fy['date_from'], fy['date_to']


def _options_from_wizard(wizard):
    return {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'partner_ids': wizard.partner_ids.ids,
        'project_ids': wizard.project_ids.ids,
        'contract_ids': wizard.contract_ids.ids,
        'sub_company_ids': wizard.sub_company_ids.ids,
        'contract_state': wizard.contract_state,
        'confirmed_only': wizard.confirmed_only,
        'show_zero_lines': wizard.show_zero_lines,
        'hide_tax_entries': wizard.hide_tax_entries,
        'unfold_all': wizard.unfold_all,
    }


class MobilizationReportWizard(models.TransientModel):
    _name = 'mobilization.report.wizard'
    _description = 'Mobilization Report Wizard'
    _inherit = 'report.drilldown.mixin'

    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(
        string='End Date',
        default=fields.Date.context_today,
        required=True,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Clients',
        domain="[('parent_id', '=', False)]",
    )
    project_ids = fields.Many2many(
        'project.project',
        string='Projects',
    )
    contract_ids = fields.Many2many(
        'ages.contract',
        string='Contracts',
    )
    sub_company_ids = fields.Many2many(
        'ages.sub.company',
        string='Active Companies',
    )
    contract_state = fields.Selection(
        [
            ('all', 'All States'),
            ('new', 'New'),
            ('running', 'Running'),
            ('closed', 'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Contract State',
        default='all',
        required=True,
    )
    confirmed_only = fields.Boolean(
        string='Confirmed Documents Only',
        default=True,
    )
    show_zero_lines = fields.Boolean(
        string='Show Zero Lines',
        default=False,
    )
    hide_tax_entries = fields.Boolean(
        string='Hide Tax Entries',
        default=False,
        help='Hide withholding / tax journal items (WTH Tax lines) from the report.',
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
    )
    unfold_all = fields.Boolean(string='Unfold All', default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('date_from') or not vals.get('date_to'):
                dummy = self.new(vals)
                date_from, date_to = _default_fiscal_dates(dummy)
                vals.setdefault('date_from', date_from)
                vals.setdefault('date_to', date_to)
        return super().create(vals_list)

    def _get_engine(self):
        self.ensure_one()
        from ..report.mobilization_report_engine import MobilizationReportEngine
        return MobilizationReportEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        return {
            'date_from': fields.Date.to_string(wizard.date_from) if wizard.date_from else False,
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'partner_ids': wizard.partner_ids.ids,
            'partner_names': wizard.partner_ids.mapped('display_name'),
            'project_ids': wizard.project_ids.ids,
            'project_names': [
                clip_project_name(name) for name in wizard.project_ids.mapped('display_name')
            ],
            'contract_ids': wizard.contract_ids.ids,
            'contract_names': wizard.contract_ids.mapped('display_name'),
            'sub_company_ids': wizard.sub_company_ids.ids,
            'sub_company_names': wizard.sub_company_ids.mapped('display_name'),
            'contract_state': wizard.contract_state,
            'confirmed_only': wizard.confirmed_only,
            'show_zero_lines': wizard.show_zero_lines,
            'hide_tax_entries': wizard.hide_tax_entries,
            'unfold_all': wizard.unfold_all,
        }

    @api.model
    def update_filters(self, wizard_id, filters):
        wizard = self.browse(wizard_id)
        vals = {}
        if 'date_from' in filters:
            vals['date_from'] = filters['date_from'] or False
        if 'date_to' in filters:
            vals['date_to'] = filters['date_to'] or fields.Date.context_today(wizard)
        if 'partner_ids' in filters:
            vals['partner_ids'] = [(6, 0, filters['partner_ids'] or [])]
        if 'project_ids' in filters:
            vals['project_ids'] = [(6, 0, filters['project_ids'] or [])]
        if 'contract_ids' in filters:
            vals['contract_ids'] = [(6, 0, filters['contract_ids'] or [])]
        if 'sub_company_ids' in filters:
            vals['sub_company_ids'] = [(6, 0, filters['sub_company_ids'] or [])]
        if 'contract_state' in filters:
            vals['contract_state'] = filters['contract_state'] or 'all'
        if 'confirmed_only' in filters:
            vals['confirmed_only'] = bool(filters['confirmed_only'])
        if 'show_zero_lines' in filters:
            vals['show_zero_lines'] = bool(filters['show_zero_lines'])
        if 'hide_tax_entries' in filters:
            vals['hide_tax_entries'] = bool(filters['hide_tax_entries'])
        if 'unfold_all' in filters:
            vals['unfold_all'] = bool(filters['unfold_all'])
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_report_data()

    @api.model
    def get_client_detail(self, wizard_id, partner_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_client_detail(partner_id)

    def _get_report_data(self):
        self.ensure_one()
        return {
            'ids': self.ids,
            'model': self._name,
            'form': _options_from_wizard(self),
        }

    def action_print_pdf(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_project_reporting.action_report_mobilization_report_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_project_reporting.action_report_mobilization_report_xlsx'
        ).report_action(self, data=data)

    def action_open_partner(self, partner_id):
        self.ensure_one()
        return self._action_open_partner(partner_id)

    def action_open_contract(self, contract_id):
        contract = self.env['ages.contract'].browse(contract_id)
        if not contract.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': contract.display_name,
            'res_model': 'ages.contract',
            'res_id': contract.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_mobilization_advance(self, advance_id):
        advance = self.env['ages.mobilization.advance'].browse(advance_id)
        if not advance.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': advance.display_name,
            'res_model': 'ages.mobilization.advance',
            'res_id': advance.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_running_bill(self, running_bill_id):
        bill = self.env['ages.running.bill'].browse(running_bill_id)
        if not bill.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': bill.display_name,
            'res_model': 'ages.running.bill',
            'res_id': bill.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_journal_entry(self, move_id):
        self.ensure_one()
        return self._action_open_journal_entry(move_id)

from odoo import models, api, fields, _

from ..report.project_directory_ledger_engine import ProjectDirectoryLedgerEngine


def _form_from_wizard(wizard):
    return {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'sub_company_id': wizard.sub_company_id.id,
        'analytic_account_id': wizard.analytic_account_id.id,
        'account_id': wizard.account_id.id,
        'partner_id': wizard.partner_id.id,
        'hide_account_payable': wizard.hide_account_payable,
        'hide_cost_of_revenue': wizard.hide_cost_of_revenue,
        'hide_bank': wizard.hide_bank,
        'target_move': wizard.target_move,
    }


class ProjectDirectoryLedgerWizard(models.TransientModel):
    _name = 'project.directory.ledger.wizard'
    _description = 'Project Directory Ledger Report Wizard'
    _inherit = 'report.drilldown.mixin'

    date_from = fields.Date(string='From Date')
    date_to = fields.Date(string='To Date')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    sub_company_id = fields.Many2one(
        'ages.sub.company',
        string='Active Company',
        domain="[('company_id', '=', company_id)]",
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Project / Analytic Account',
    )
    account_id = fields.Many2one('account.account', string='Account (COA)')
    partner_id = fields.Many2one('res.partner', string='Partner / Vendor')
    hide_account_payable = fields.Boolean(
        string='Hide 211000 Account Payable',
        default=True,
        help='When enabled, journal lines posted on account 211000 are excluded from the report.',
    )
    hide_cost_of_revenue = fields.Boolean(
        string='Hide Cost of Revenue',
        default=True,
        help='When enabled, Cost of Revenue lines are excluded from the report.',
    )
    hide_bank = fields.Boolean(
        string='Hide Bank',
        default=True,
        help='When enabled, bank and cash payment lines are excluded from the report.',
    )
    target_move = fields.Selection(
        [
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('all', 'All'),
        ],
        string='Entries',
        default='posted',
        required=True,
    )

    @api.onchange('sub_company_id')
    def _onchange_sub_company_id(self):
        domain = []
        if self.sub_company_id:
            domain = [('ages_contract_id.sub_company_id', '=', self.sub_company_id.id)]
            if (
                self.analytic_account_id
                and self.analytic_account_id.ages_contract_id
                and self.analytic_account_id.ages_contract_id.sub_company_id != self.sub_company_id
            ):
                self.analytic_account_id = False
        return {'domain': {'analytic_account_id': domain}}

    def action_open_interactive_report(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'project_directory_ledger_report',
            'name': _('Project Directory Ledger'),
            'params': {'wizard_id': self.id},
        }

    def _get_report_data(self):
        self.ensure_one()
        return {
            'ids': self.ids,
            'model': self._name,
            'form': _form_from_wizard(self),
        }

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        return {
            'date_from': fields.Date.to_string(wizard.date_from) if wizard.date_from else False,
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'sub_company_id': wizard.sub_company_id.id,
            'sub_company_name': wizard.sub_company_id.display_name,
            'analytic_account_id': wizard.analytic_account_id.id,
            'analytic_account_name': wizard.analytic_account_id.display_name,
            'account_id': wizard.account_id.id,
            'account_name': wizard.account_id.display_name,
            'partner_id': wizard.partner_id.id,
            'partner_name': wizard.partner_id.display_name,
            'hide_account_payable': wizard.hide_account_payable,
            'hide_cost_of_revenue': wizard.hide_cost_of_revenue,
            'hide_bank': wizard.hide_bank,
            'target_move': wizard.target_move or 'posted',
        }

    @api.model
    def update_filters(self, wizard_id, filters):
        wizard = self.browse(wizard_id)
        vals = {}
        if 'date_from' in filters:
            vals['date_from'] = filters['date_from'] or False
        if 'date_to' in filters:
            vals['date_to'] = filters['date_to'] or False
        if 'sub_company_id' in filters:
            vals['sub_company_id'] = filters['sub_company_id'] or False
        if 'analytic_account_id' in filters:
            vals['analytic_account_id'] = filters['analytic_account_id'] or False
        if 'account_id' in filters:
            vals['account_id'] = filters['account_id'] or False
        if 'partner_id' in filters:
            vals['partner_id'] = filters['partner_id'] or False
        if 'hide_account_payable' in filters:
            vals['hide_account_payable'] = bool(filters['hide_account_payable'])
        if 'hide_cost_of_revenue' in filters:
            vals['hide_cost_of_revenue'] = bool(filters['hide_cost_of_revenue'])
        if 'hide_bank' in filters:
            vals['hide_bank'] = bool(filters['hide_bank'])
        if 'target_move' in filters:
            vals['target_move'] = filters['target_move'] or 'posted'
        # Clear project when Active Company changes and project no longer matches
        if vals.get('sub_company_id') and 'analytic_account_id' not in filters:
            aa = wizard.analytic_account_id
            if aa and aa.ages_contract_id and aa.ages_contract_id.sub_company_id.id != vals['sub_company_id']:
                vals['analytic_account_id'] = False
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id)
        engine = ProjectDirectoryLedgerEngine(self.env, _form_from_wizard(wizard))
        data = engine.get_report_data()
        return {
            'lines': data['lines'],
            'group_by': data['group_by'],
            'group_by_label': data['group_by_label'],
            'show_analytic_col': data['show_analytic_col'],
            'currency_id': data['currency_id'],
            'date_label': data['date_label'],
            'filter_labels': data['filter_labels'],
            'grand_totals': data['grand_totals'],
            'group_count': data['group_count'],
            'line_count': data['line_count'],
        }

    def action_print_pdf(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_project_directory_ledger_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_project_directory_ledger_xlsx'
        ).report_action(self, data=data)

    def action_preview_html(self):
        data = self._get_report_data()
        action = self.env.ref(
            'ages_custom_reports.action_report_project_directory_ledger_pdf'
        ).report_action(self, data=data)
        action['target'] = 'main'
        action['report_type'] = 'qweb-html'
        return action

from odoo import models, fields, api, _
from odoo.exceptions import MissingError

from ..report.report_display import clip_project_name


def _default_fiscal_dates(wizard):
    today = fields.Date.context_today(wizard)
    fy = wizard.env.company.compute_fiscalyear_dates(today)
    return fy['date_from'], fy['date_to']


def _options_from_wizard(wizard):
    options = {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'target_move': wizard.target_move,
        'partner_ids': wizard.partner_ids.ids,
        'account_ids': wizard.account_ids.ids or False,
        'journal_ids': wizard.journal_ids.ids,
        'analytic_account_id': wizard.analytic_account_id.id,
        'analytic_account_name': clip_project_name(wizard.analytic_account_id.display_name),
        'account_filters': wizard.account_filter_list(),
        'unfold_all': wizard.unfold_all,
    }
    if 'show_opal_balance' in wizard._fields:
        options['show_opal_balance'] = bool(wizard.show_opal_balance)
    return options


class PartnerLedgerWizard(models.TransientModel):
    _name = 'partner.ledger.wizard'
    _description = 'Partner Ledger Wizard'
    _inherit = 'report.drilldown.mixin'

    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(
        string='End Date',
        default=fields.Date.context_today,
        required=True,
    )
    target_move = fields.Selection(
        [
            ('posted', 'Posted Entries'),
            ('all', 'All Entries'),
        ],
        string='Target Moves',
        default='posted',
        required=True,
    )
    filter_receivable = fields.Boolean(string='Receivable', default=True)
    filter_non_trade_receivable = fields.Boolean(string='Non Trade Receivable', default=False)
    filter_payable = fields.Boolean(string='Payable', default=True)
    filter_non_trade_payable = fields.Boolean(string='Non Trade Payable', default=False)
    partner_ids = fields.Many2many(
        'res.partner',
        string='Partners',
    )
    account_ids = fields.Many2many(
        'account.account',
        string='Accounts',
    )
    journal_ids = fields.Many2many(
        'account.journal',
        string='Journals',
        domain="[('company_id', '=', company_id)]",
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Project',
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

    def account_filter_list(self):
        self.ensure_one()
        filters = []
        if self.filter_receivable:
            filters.append('receivable')
        if self.filter_non_trade_receivable:
            filters.append('non_trade_receivable')
        if self.filter_payable:
            filters.append('payable')
        if self.filter_non_trade_payable:
            filters.append('non_trade_payable')
        return filters

    def _get_engine(self):
        self.ensure_one()
        from ..report.partner_ledger_engine import PartnerLedgerEngine
        return PartnerLedgerEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id).exists()
        if not wizard:
            return {}
        return {
            'date_from': fields.Date.to_string(wizard.date_from) if wizard.date_from else False,
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'target_move': wizard.target_move,
            'partner_ids': wizard.partner_ids.ids,
            'partner_names': wizard.partner_ids.mapped('display_name'),
            'account_ids': wizard.account_ids.ids,
            'account_names': wizard.account_ids.mapped('display_name'),
            'journal_ids': wizard.journal_ids.ids,
            'journal_names': wizard.journal_ids.mapped('display_name'),
            'analytic_account_id': wizard.analytic_account_id.id,
            'analytic_account_name': clip_project_name(wizard.analytic_account_id.display_name),
            'filter_receivable': wizard.filter_receivable,
            'filter_non_trade_receivable': wizard.filter_non_trade_receivable,
            'filter_payable': wizard.filter_payable,
            'filter_non_trade_payable': wizard.filter_non_trade_payable,
            'unfold_all': wizard.unfold_all,
        }

    @api.model
    def update_filters(self, wizard_id, filters):
        wizard = self.browse(wizard_id).exists()
        if not wizard:
            raise MissingError(_('The report wizard expired. Please reopen the report.'))
        vals = {}
        if 'date_from' in filters:
            vals['date_from'] = filters['date_from'] or False
        if 'date_to' in filters:
            vals['date_to'] = filters['date_to'] or fields.Date.context_today(wizard)
        if 'target_move' in filters:
            vals['target_move'] = filters['target_move'] or 'posted'
        if 'partner_ids' in filters:
            vals['partner_ids'] = [(6, 0, filters['partner_ids'] or [])]
        if 'account_ids' in filters:
            vals['account_ids'] = [(6, 0, filters['account_ids'] or [])]
        if 'journal_ids' in filters:
            vals['journal_ids'] = [(6, 0, filters['journal_ids'] or [])]
        if 'analytic_account_id' in filters:
            vals['analytic_account_id'] = filters['analytic_account_id'] or False
        if 'filter_receivable' in filters:
            vals['filter_receivable'] = bool(filters['filter_receivable'])
        if 'filter_non_trade_receivable' in filters:
            vals['filter_non_trade_receivable'] = bool(filters['filter_non_trade_receivable'])
        if 'filter_payable' in filters:
            vals['filter_payable'] = bool(filters['filter_payable'])
        if 'filter_non_trade_payable' in filters:
            vals['filter_non_trade_payable'] = bool(filters['filter_non_trade_payable'])
        if 'unfold_all' in filters:
            vals['unfold_all'] = bool(filters['unfold_all'])
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_report_data()

    @api.model
    def get_partner_detail(self, wizard_id, partner_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_partner_detail(partner_id)

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
            'ages_custom_reports.action_report_partner_ledger_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_partner_ledger_xlsx'
        ).report_action(self, data=data)

    def action_open_partner(self, partner_id):
        self.ensure_one()
        return self._action_open_partner(partner_id)

    def action_open_journal_items(self, partner_id):
        self.ensure_one()
        return self._action_open_journal_items_for_partner(
            partner_id,
            date_from=self.date_from,
            date_to=self.date_to,
            target_move=self.target_move,
            analytic_account_id=self.analytic_account_id.id,
        )

    def action_open_journal_entry(self, move_id):
        self.ensure_one()
        return self._action_open_journal_entry(move_id)

    @api.model
    def action_open_journal_entry_from_line(self, move_line_id):
        return super().action_open_journal_entry_from_line(move_line_id)

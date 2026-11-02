from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

from ..report.report_display import clip_project_name


def _default_month_dates(wizard):
    today = fields.Date.context_today(wizard)
    date_from = today.replace(day=1)
    date_to = date_from + relativedelta(months=1, days=-1)
    return date_from, date_to


def _options_from_wizard(wizard):
    options = {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'target_move': wizard.target_move,
        'journal_ids': wizard.journal_ids.ids,
        'analytic_account_id': wizard.analytic_account_id.id,
        'analytic_account_name': clip_project_name(wizard.analytic_account_id.display_name),
        'unfold_all': wizard.unfold_all,
        'account_ids': wizard.account_ids.ids or False,
    }
    if 'show_opal_balance' in wizard._fields:
        options['show_opal_balance'] = bool(wizard.show_opal_balance)
    return options


class GeneralLedgerWizard(models.TransientModel):
    _name = 'general.ledger.wizard'
    _description = 'General Ledger Report Wizard'
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
    journal_ids = fields.Many2many(
        'account.journal',
        string='Journals',
        domain="[('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
    )
    account_ids = fields.Many2many(
        'account.account',
        string='Accounts',
    )
    unfold_all = fields.Boolean(string='Unfold All', default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('date_from') or not vals.get('date_to'):
                dummy = self.new(vals)
                date_from, date_to = _default_month_dates(dummy)
                vals.setdefault('date_from', date_from)
                vals.setdefault('date_to', date_to)
        return super().create(vals_list)

    def _get_engine(self):
        self.ensure_one()
        from ..report.general_ledger_engine import GeneralLedgerEngine
        return GeneralLedgerEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        return {
            'date_from': fields.Date.to_string(wizard.date_from) if wizard.date_from else False,
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'target_move': wizard.target_move,
            'journal_ids': wizard.journal_ids.ids,
            'journal_names': wizard.journal_ids.mapped('display_name'),
            'analytic_account_id': wizard.analytic_account_id.id,
            'analytic_account_name': clip_project_name(wizard.analytic_account_id.display_name),
            'account_ids': wizard.account_ids.ids,
            'account_names': wizard.account_ids.mapped('display_name'),
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
        if 'target_move' in filters:
            vals['target_move'] = filters['target_move'] or 'posted'
        if 'journal_ids' in filters:
            vals['journal_ids'] = [(6, 0, filters['journal_ids'] or [])]
        if 'analytic_account_id' in filters:
            vals['analytic_account_id'] = filters['analytic_account_id'] or False
        if 'account_ids' in filters:
            vals['account_ids'] = [(6, 0, filters['account_ids'] or [])]
        if 'unfold_all' in filters:
            vals['unfold_all'] = bool(filters['unfold_all'])
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_report_data()

    @api.model
    def get_account_detail(self, wizard_id, account_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_account_detail(account_id)

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
            'ages_custom_reports.action_report_general_ledger_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_general_ledger_xlsx'
        ).report_action(self, data=data)

    def action_open_journal_items(self, account_id):
        self.ensure_one()
        return self._action_open_journal_items_for_account(
            account_id,
            date_from=self.date_from,
            date_to=self.date_to,
            target_move=self.target_move,
        )

    def action_open_journal_entry(self, move_id):
        self.ensure_one()
        return self._action_open_journal_entry(move_id)

    @api.model
    def action_open_journal_entry_from_line(self, move_line_id):
        return super().action_open_journal_entry_from_line(move_line_id)

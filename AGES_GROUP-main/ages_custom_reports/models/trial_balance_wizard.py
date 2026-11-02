from odoo import models, fields, api
from dateutil.relativedelta import relativedelta


def _default_month_dates(wizard):
    today = fields.Date.context_today(wizard)
    date_from = today.replace(day=1)
    date_to = date_from + relativedelta(months=1, days=-1)
    return date_from, date_to


def _options_from_wizard(wizard):
    return {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'target_move': wizard.target_move,
        'journal_ids': wizard.journal_ids.ids,
        'analytic_account_id': wizard.analytic_account_id.id,
        'unfold_all': wizard.unfold_all,
        'hierarchy': wizard.hierarchy,
        'hide_zero_lines': wizard.hide_zero_lines,
    }


class TrialBalanceWizard(models.TransientModel):
    _name = 'trial.balance.wizard'
    _description = 'Trial Balance Report Wizard'
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
    unfold_all = fields.Boolean(string='Unfold All', default=False)
    hierarchy = fields.Boolean(string='Hierarchy and Subtotals', default=True)
    hide_zero_lines = fields.Boolean(string='Hide Zero Lines', default=False)

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
        from ..report.trial_balance_engine import TrialBalanceEngine
        return TrialBalanceEngine(self.env, _options_from_wizard(self))

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
            'analytic_account_name': wizard.analytic_account_id.display_name,
            'unfold_all': wizard.unfold_all,
            'hierarchy': wizard.hierarchy,
            'hide_zero_lines': wizard.hide_zero_lines,
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
        if 'unfold_all' in filters:
            vals['unfold_all'] = bool(filters['unfold_all'])
        if 'hierarchy' in filters:
            vals['hierarchy'] = bool(filters['hierarchy'])
        if 'hide_zero_lines' in filters:
            vals['hide_zero_lines'] = bool(filters['hide_zero_lines'])
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_report_data()

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
            'ages_custom_reports.action_report_trial_balance_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_trial_balance_xlsx'
        ).report_action(self, data=data)

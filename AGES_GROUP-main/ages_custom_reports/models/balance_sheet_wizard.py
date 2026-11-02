from odoo import models, fields, api, _


def _options_from_wizard(wizard):
    return {
        'date_to': wizard.date_to or fields.Date.context_today(wizard),
        'target_move': wizard.target_move,
        'journal_ids': wizard.journal_ids.ids,
        'analytic_account_id': wizard.analytic_account_id.id,
        'unfold_all': wizard.unfold_all,
    }


class BalanceSheetWizard(models.TransientModel):
    _name = 'balance.sheet.wizard'
    _description = 'Balance Sheet Report Wizard'
    _inherit = 'report.drilldown.mixin'

    date_to = fields.Date(
        string='As of Date',
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
    unfold_all = fields.Boolean(string='Unfold All', default=True)

    def _get_engine(self):
        self.ensure_one()
        from ..report.balance_sheet_engine import BalanceSheetEngine
        return BalanceSheetEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        return {
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'target_move': wizard.target_move,
            'journal_ids': wizard.journal_ids.ids,
            'journal_names': wizard.journal_ids.mapped('display_name'),
            'analytic_account_id': wizard.analytic_account_id.id,
            'analytic_account_name': wizard.analytic_account_id.display_name,
            'unfold_all': wizard.unfold_all,
            'company_id': wizard.company_id.id,
        }

    @api.model
    def update_filters(self, wizard_id, filters):
        wizard = self.browse(wizard_id)
        vals = {}
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

    def action_open_interactive_report(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'ages_balance_sheet_report',
            'name': _('Balance Sheet'),
            'params': {'wizard_id': self.id},
        }

    def action_print_pdf(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_balance_sheet_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_balance_sheet_xlsx'
        ).report_action(self, data=data)

    def action_open_general_ledger(self, account_id):
        self.ensure_one()
        return self._action_open_interactive_general_ledger(
            account_id,
            date_from=False,
            date_to=self.date_to,
            target_move=self.target_move,
            journal_ids=self.journal_ids.ids,
            analytic_account_id=self.analytic_account_id.id,
            parent_name=_('Balance Sheet'),
        )

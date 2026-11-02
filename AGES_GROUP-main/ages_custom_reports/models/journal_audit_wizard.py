from odoo import models, fields, api, _


def _default_fiscal_dates(wizard):
    today = fields.Date.context_today(wizard)
    fy = wizard.env.company.compute_fiscalyear_dates(today)
    return fy['date_from'], fy['date_to']


def _options_from_wizard(wizard):
    return {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'target_move': wizard.target_move,
        'journal_ids': wizard.journal_ids.ids,
        'unfold_all': wizard.unfold_all,
    }


class JournalAuditWizard(models.TransientModel):
    _name = 'journal.audit.wizard'
    _description = 'Journal Audit Wizard'
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
        from ..report.journal_audit_engine import JournalAuditEngine
        return JournalAuditEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        return {
            'date_from': fields.Date.to_string(wizard.date_from) if wizard.date_from else False,
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'target_move': wizard.target_move,
            'journal_ids': wizard.journal_ids.ids,
            'journal_names': wizard.journal_ids.mapped('display_name'),
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
        if 'unfold_all' in filters:
            vals['unfold_all'] = bool(filters['unfold_all'])
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_report_data()

    @api.model
    def get_journal_accounts(self, wizard_id, journal_id):
        wizard = self.browse(wizard_id)
        return wizard._get_engine().get_journal_accounts(journal_id)

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
            'ages_custom_reports.action_report_journal_audit_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_journal_audit_xlsx'
        ).report_action(self, data=data)

    def action_open_journal_audit(self, journal_id):
        self.ensure_one()
        domain = [('journal_id', '=', journal_id)]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        domain.append(('date', '<=', self.date_to))
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        journal = self.env['account.journal'].browse(journal_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Audit: %s', journal.display_name),
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def action_open_account_lines(self, journal_id, account_id):
        self.ensure_one()
        domain = [
            ('journal_id', '=', journal_id),
            ('account_id', '=', account_id),
        ]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        domain.append(('date', '<=', self.date_to))
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        account = self.env['account.account'].browse(account_id)
        return {
            'type': 'ir.actions.act_window',
            'name': account.display_name,
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def action_open_tax_audit(self, tax_id):
        self.ensure_one()
        domain = [('tax_line_id', '=', tax_id)]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        domain.append(('date', '<=', self.date_to))
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Audit'),
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def action_open_tax_grid_audit(self, tag_ids):
        self.ensure_one()
        domain = [('tax_tag_ids', 'in', tag_ids or [])]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        domain.append(('date', '<=', self.date_to))
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Grid Audit'),
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

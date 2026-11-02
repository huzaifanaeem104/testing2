# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _options_from_wizard(wizard):
    return {
        'report_type': wizard.report_type,
        'date_to': wizard.date_to,
        'aging_based_on': wizard.aging_based_on,
        'aging_interval': wizard.aging_interval,
        'partner_ids': wizard.partner_ids.ids,
        'partner_category_ids': wizard.partner_category_ids.ids,
        'filter_trade': wizard.filter_trade,
        'filter_non_trade': wizard.filter_non_trade,
        'all_entries': wizard.all_entries,
        'show_currency': wizard.show_currency,
        'show_account': wizard.show_account,
        'hide_zero_lines': wizard.hide_zero_lines,
        'unfold_all': wizard.unfold_all,
        'sort_by': wizard.sort_by,
        'sort_direction': wizard.sort_direction,
    }


class AgedPartnerBalanceWizard(models.TransientModel):
    _name = 'aged.partner.balance.wizard'
    _description = 'Aged Receivable and Payable Wizard'
    _inherit = 'report.drilldown.mixin'

    report_type = fields.Selection(
        [
            ('receivable', 'Aged Receivable'),
            ('payable', 'Aged Payable'),
        ],
        required=True,
        default='receivable',
    )
    date_to = fields.Date(
        string='As of',
        required=True,
        default=fields.Date.context_today,
    )
    aging_based_on = fields.Selection(
        [
            ('maturity', 'Due Date'),
            ('invoice', 'Invoice Date'),
        ],
        required=True,
        default='maturity',
    )
    aging_interval = fields.Integer(
        string='Period Length',
        required=True,
        default=30,
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Partners',
    )
    partner_category_ids = fields.Many2many(
        'res.partner.category',
        string='Tags',
    )
    filter_trade = fields.Boolean(
        string='Trade',
        default=True,
    )
    filter_non_trade = fields.Boolean(
        string='Non-Trade',
        default=False,
    )
    all_entries = fields.Boolean(string='Draft Entries')
    show_currency = fields.Boolean(string='Show Currency')
    show_account = fields.Boolean(string='Show Account')
    hide_zero_lines = fields.Boolean(string='Hide zero lines')
    unfold_all = fields.Boolean(string='Unfold All')
    sort_by = fields.Selection(
        [
            ('name', 'Partner'),
            ('invoice_date', 'Invoice Date'),
            ('period0', 'At Date'),
            ('period1', 'Period 1'),
            ('period2', 'Period 2'),
            ('period3', 'Period 3'),
            ('period4', 'Period 4'),
            ('period5', 'Older'),
            ('total', 'Total'),
        ],
        default='name',
        required=True,
    )
    sort_direction = fields.Selection(
        [('asc', 'Ascending'), ('desc', 'Descending')],
        default='asc',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
    )

    @api.constrains('aging_interval')
    def _check_aging_interval(self):
        for wizard in self:
            if wizard.aging_interval < 1:
                raise ValidationError(_('The aging interval must be at least one day.'))

    def _get_engine(self):
        self.ensure_one()
        from ..report.aged_partner_balance_engine import AgedPartnerBalanceEngine
        return AgedPartnerBalanceEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id).exists()
        if not wizard:
            return {}
        return {
            'report_type': wizard.report_type,
            'date_to': fields.Date.to_string(wizard.date_to),
            'aging_based_on': wizard.aging_based_on,
            'aging_interval': wizard.aging_interval,
            'partner_ids': wizard.partner_ids.ids,
            'partner_names': wizard.partner_ids.mapped('display_name'),
            'partner_category_ids': wizard.partner_category_ids.ids,
            'filter_trade': wizard.filter_trade,
            'filter_non_trade': wizard.filter_non_trade,
            'all_entries': wizard.all_entries,
            'show_currency': wizard.show_currency,
            'show_account': wizard.show_account,
            'hide_zero_lines': wizard.hide_zero_lines,
            'unfold_all': wizard.unfold_all,
            'sort_by': wizard.sort_by,
            'sort_direction': wizard.sort_direction,
        }

    @api.model
    def update_filters(self, wizard_id, filters):
        wizard = self.browse(wizard_id).exists()
        if not wizard:
            return False
        vals = {}
        scalar_fields = (
            'report_type',
            'aging_based_on',
            'sort_by',
            'sort_direction',
        )
        for field_name in scalar_fields:
            if field_name in filters and filters[field_name]:
                vals[field_name] = filters[field_name]
        if 'date_to' in filters:
            vals['date_to'] = (
                filters['date_to'] or fields.Date.context_today(wizard)
            )
        if 'aging_interval' in filters:
            vals['aging_interval'] = max(int(filters['aging_interval'] or 30), 1)
        if 'partner_ids' in filters:
            vals['partner_ids'] = [(6, 0, filters['partner_ids'] or [])]
        if 'partner_category_ids' in filters:
            vals['partner_category_ids'] = [(6, 0, filters['partner_category_ids'] or [])]
        for field_name in (
            'filter_trade',
            'filter_non_trade',
            'all_entries',
            'show_currency',
            'show_account',
            'hide_zero_lines',
            'unfold_all',
        ):
            if field_name in filters:
                vals[field_name] = bool(filters[field_name])
        return wizard._write_filters(vals)

    @api.model
    def get_report_lines(self, wizard_id):
        wizard = self.browse(wizard_id).exists()
        return wizard._get_engine().get_report_data() if wizard else {}

    @api.model
    def get_partner_detail(self, wizard_id, partner_id=False):
        wizard = self.browse(wizard_id).exists()
        if not wizard:
            return {'children': []}
        return wizard._get_engine().get_partner_detail(partner_id)

    def _get_report_data(self):
        self.ensure_one()
        return {
            'ids': self.ids,
            'model': self._name,
            'form': _options_from_wizard(self),
        }

    def action_print_pdf(self):
        self.ensure_one()
        xmlid = (
            'ages_custom_reports.action_report_aged_receivable_pdf'
            if self.report_type == 'receivable'
            else 'ages_custom_reports.action_report_aged_payable_pdf'
        )
        return self.env.ref(xmlid).report_action(self, data=self._get_report_data())

    def action_print_excel(self):
        self.ensure_one()
        xmlid = (
            'ages_custom_reports.action_report_aged_receivable_xlsx'
            if self.report_type == 'receivable'
            else 'ages_custom_reports.action_report_aged_payable_xlsx'
        )
        return self.env.ref(xmlid).report_action(self, data=self._get_report_data())

    def action_open_interactive_report(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'ages_aged_partner_balance_report',
            'name': dict(self._fields['report_type'].selection)[self.report_type],
            'params': {
                'wizard_id': self.id,
                'report_type': self.report_type,
            },
        }

    def action_open_partner(self, partner_id):
        self.ensure_one()
        return self._action_open_partner(partner_id)

    def action_open_partner_ledger(self, partner_id):
        self.ensure_one()
        vals = {
            'date_from': False,
            'date_to': self.date_to,
            'target_move': 'all' if self.all_entries else 'posted',
            'partner_ids': [(6, 0, [partner_id])] if partner_id else [(5, 0, 0)],
            'filter_receivable': self.report_type == 'receivable' and self.filter_trade,
            'filter_non_trade_receivable': (
                self.report_type == 'receivable' and self.filter_non_trade
            ),
            'filter_payable': self.report_type == 'payable' and self.filter_trade,
            'filter_non_trade_payable': (
                self.report_type == 'payable' and self.filter_non_trade
            ),
            'unfold_all': True,
        }
        partner_ledger = self.env['partner.ledger.wizard'].create(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'ages_partner_ledger_report',
            'name': _('Partner Ledger'),
            'params': {'wizard_id': partner_ledger.id},
        }

    def action_open_bucket(self, partner_id=False, period_key='total'):
        self.ensure_one()
        move_line_ids = self._get_engine().get_bucket_move_line_ids(
            partner_id,
            period_key,
        )
        partner = (
            self.env['res.partner'].browse(partner_id)
            if partner_id
            else self.env['res.partner']
        )
        period_label = self._get_engine()._period_labels().get(
            period_key,
            _('Total'),
        )
        partner_label = partner.display_name if partner else _('Unknown')
        return {
            'type': 'ir.actions.act_window',
            'name': _('%(partner)s — %(period)s', partner=partner_label, period=period_label),
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': [('id', 'in', move_line_ids or [0])],
            'context': {
                **self.env.context,
                'create': False,
                'search_default_group_by_partner': 0,
            },
            'target': 'current',
        }

    def action_open_journal_entry(self, move_id, move_line_id=None):
        self.ensure_one()
        return self._action_open_journal_entry(move_id, move_line_id)

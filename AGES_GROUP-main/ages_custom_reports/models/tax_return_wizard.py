from odoo import models, fields, api, _
from odoo.exceptions import UserError, RedirectWarning
from dateutil.relativedelta import relativedelta


def _default_month_dates(wizard):
    today = fields.Date.context_today(wizard)
    company = wizard.company_id or wizard.env.company
    if hasattr(company, '_get_tax_closing_period_boundaries'):
        return company._get_tax_closing_period_boundaries(today)
    date_from = today.replace(day=1)
    date_to = date_from + relativedelta(months=1, days=-1)
    return date_from, date_to


def _options_from_wizard(wizard):
    return {
        'date_from': wizard.date_from,
        'date_to': wizard.date_to,
        'target_move': wizard.target_move,
        'comparison': wizard.comparison,
        'unfold_all': wizard.unfold_all,
    }


class TaxReturnWizard(models.TransientModel):
    _name = 'tax.return.wizard'
    _description = 'Tax Return Report Wizard'
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
    comparison = fields.Boolean(string='% Comparison', default=False)
    unfold_all = fields.Boolean(string='Unfold All', default=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
    )

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
        from ..report.tax_return_engine import TaxReturnEngine
        return TaxReturnEngine(self.env, _options_from_wizard(self))

    @api.model
    def get_filter_values(self, wizard_id):
        wizard = self.browse(wizard_id)
        return {
            'date_from': fields.Date.to_string(wizard.date_from) if wizard.date_from else False,
            'date_to': fields.Date.to_string(wizard.date_to) if wizard.date_to else False,
            'target_move': wizard.target_move,
            'comparison': wizard.comparison,
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
        if 'comparison' in filters:
            vals['comparison'] = bool(filters['comparison'])
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

    def action_print_pdf(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_tax_return_pdf'
        ).report_action(self, data=data)

    def action_print_excel(self):
        data = self._get_report_data()
        return self.env.ref(
            'ages_custom_reports.action_report_tax_return_xlsx'
        ).report_action(self, data=data)

    @api.model
    def action_open_unposted_moves(self, wizard_id):
        wizard = self.browse(wizard_id)
        domain = [
            ('company_id', 'child_of', wizard.company_id.id),
            ('state', '=', 'draft'),
            ('date', '<=', wizard.date_to),
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Unposted Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            'context': {'search_default_unposted': 1},
        }

    @api.model
    def action_open_tax_lines(self, wizard_id, tag_ids, column='tax'):
        wizard = self.browse(wizard_id)
        domain = [
            ('company_id', 'child_of', wizard.company_id.id),
            ('tax_tag_ids', 'in', tag_ids or []),
            ('date', '<=', wizard.date_to),
        ]
        if wizard.date_from:
            domain.append(('date', '>=', wizard.date_from))
        if wizard.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        name = _('Tax Amount') if column == 'tax' else _('Base')
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def action_closing_entry(self):
        self.ensure_one()
        move = self._get_or_create_closing_entry()
        return {
            'type': 'ir.actions.act_window',
            'name': move.display_name,
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'views': [(self.env.ref('account.view_move_form').id, 'form')],
            'target': 'current',
        }

    def _closing_ref(self):
        self.ensure_one()
        return 'TAX-CLOSE-%s-%s' % (
            fields.Date.to_string(self.date_from),
            fields.Date.to_string(self.date_to),
        )

    def _get_or_create_closing_entry(self):
        self.ensure_one()
        existing = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('ref', '=', self._closing_ref()),
            ('state', '=', 'draft'),
        ], limit=1)
        if existing:
            return existing
        return self._create_closing_entry()

    def _create_closing_entry(self):
        self.ensure_one()
        journal = self.company_id._get_tax_closing_journal()
        if not journal:
            raise UserError(_(
                'Please configure a miscellaneous journal to create the Tax Closing Entry.'
            ))

        domain = [
            ('company_id', 'child_of', self.company_id.id),
            ('tax_line_id', '!=', False),
            ('tax_repartition_line_id.use_in_tax_closing', '=', True),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('date', '<=', self.date_to),
            ('parent_state', '=', 'posted'),
        ]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))

        groups = self.env['account.move.line'].read_group(
            domain,
            ['balance:sum', 'account_id', 'tax_line_id'],
            ['account_id', 'tax_line_id'],
            lazy=False,
        )
        if not groups:
            raise UserError(_(
                'There are no tax lines to close for the selected period.'
            ))

        taxes = self.env['account.tax'].browse({
            group['tax_line_id'][0]
            for group in groups
            if group.get('tax_line_id')
        })
        tax_by_id = {tax.id: tax for tax in taxes}
        countries = taxes.mapped('country_id') | self.company_id.account_fiscal_country_id
        if self.env['account.tax.group']._check_misconfigured_tax_groups(
            self.company_id, countries,
        ):
            action = {
                'type': 'ir.actions.act_window',
                'name': _('Tax groups'),
                'res_model': 'account.tax.group',
                'view_mode': 'list',
                'views': [[False, 'list']],
                'domain': [
                    '|',
                    ('country_id', 'in', countries.ids),
                    ('country_id', '=', False),
                ],
            }
            raise RedirectWarning(
                _('Please specify the accounts necessary for the Tax Closing Entry.'),
                action,
                _('Configure your TAX accounts - %s', self.company_id.display_name),
            )

        line_vals = []
        totals_by_group = {}
        currency = self.company_id.currency_id
        for group in groups:
            if not group.get('account_id') or not group.get('tax_line_id'):
                continue
            tax = tax_by_id.get(group['tax_line_id'][0])
            if not tax:
                continue
            tax_group = tax.tax_group_id
            if not tax_group.tax_payable_account_id or not tax_group.tax_receivable_account_id:
                continue
            amount = group['balance'] or 0.0
            if currency.is_zero(amount):
                continue
            line_vals.append((0, 0, {
                'name': tax.display_name,
                'debit': abs(amount) if amount < 0 else 0.0,
                'credit': amount if amount > 0 else 0.0,
                'account_id': group['account_id'][0],
            }))
            totals_by_group.setdefault(tax_group, 0.0)
            totals_by_group[tax_group] += amount

        if not line_vals:
            raise UserError(_(
                'There are no tax balances to close for the selected period.'
            ))

        for tax_group, total in totals_by_group.items():
            if currency.is_zero(total):
                continue
            if total < 0:
                line_vals.append((0, 0, {
                    'name': _('Payable tax amount'),
                    'debit': 0.0,
                    'credit': abs(total),
                    'account_id': tax_group.tax_payable_account_id.id,
                }))
            else:
                line_vals.append((0, 0, {
                    'name': _('Receivable tax amount'),
                    'debit': total,
                    'credit': 0.0,
                    'account_id': tax_group.tax_receivable_account_id.id,
                }))

        period_label = self.date_from.strftime('%b %Y') if self.date_from else fields.Date.to_string(self.date_to)
        return self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.date_to,
            'ref': self._closing_ref(),
            'company_id': self.company_id.id,
            'line_ids': line_vals,
            'narration': _('Tax Return closing entry for %s', period_label),
        })

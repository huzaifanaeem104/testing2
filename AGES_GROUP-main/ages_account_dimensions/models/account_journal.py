# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.tools.misc import formatLang
from odoo.tools.safe_eval import safe_eval


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    code = fields.Char(size=10)

    @api.model
    def ages_get_overview_kpis(self):
        """Year-to-date accounting KPIs for the company dashboard strip."""
        self.check_access_rights('read')
        company = self.env.company
        currency = company.currency_id
        today = fields.Date.context_today(self)
        year_start = today.replace(month=1, day=1)
        MoveLine = self.env['account.move.line'].sudo()
        Move = self.env['account.move'].sudo()

        def _group_sum(domain):
            rows = MoveLine._read_group(domain=domain, aggregates=['balance:sum'])
            return (rows[0][0] or 0.0) if rows else 0.0

        common = [
            ('company_id', '=', company.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', year_start),
            ('date', '<=', today),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        income = -_group_sum(common + [('account_id.internal_group', '=', 'income')])
        expense = _group_sum(common + [('account_id.internal_group', '=', 'expense')])
        cogs = _group_sum(common + [('account_id.account_type', '=', 'expense_direct_cost')])
        gross = income - cogs
        net = income - expense

        cash_groups = MoveLine._read_group(
            domain=common + [('account_id.account_type', '=', 'asset_cash')],
            aggregates=['debit:sum', 'credit:sum'],
        )
        cash_in = (cash_groups[0][0] or 0.0) if cash_groups else 0.0
        cash_out = (cash_groups[0][1] or 0.0) if cash_groups else 0.0

        unpaid_in = Move._read_group(
            domain=[
                ('company_id', '=', company.id),
                ('state', '=', 'posted'),
                ('move_type', 'in', ('out_invoice', 'out_refund', 'out_receipt')),
                ('payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
            ],
            aggregates=['amount_residual_signed:sum'],
        )
        unpaid_out = Move._read_group(
            domain=[
                ('company_id', '=', company.id),
                ('state', '=', 'posted'),
                ('move_type', 'in', ('in_invoice', 'in_refund', 'in_receipt')),
                ('payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
            ],
            aggregates=['amount_residual_signed:sum'],
        )
        unpaid_customers = unpaid_in[0][0] if unpaid_in else 0.0
        unpaid_suppliers = abs(unpaid_out[0][0] if unpaid_out else 0.0)

        def fmt(amount):
            return formatLang(self.env, amount, currency_obj=currency)

        return {
            'currency_symbol': currency.symbol or '',
            'gross_margin': fmt(gross),
            'revenue': fmt(income),
            'net_margin': fmt(net),
            'expenses': fmt(expense),
            'unpaid_customers': fmt(unpaid_customers),
            'unpaid_suppliers': fmt(unpaid_suppliers),
            'cash_in': fmt(cash_in),
            'cash_out': fmt(cash_out),
        }

    def _ages_overview_period(self):
        today = fields.Date.context_today(self)
        return today.replace(month=1, day=1), today

    def _ages_overview_aml_base(self):
        date_from, date_to = self._ages_overview_period()
        return [
            ('company_id', '=', self.env.company.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

    def _ages_merge_action_context(self, action, **extra):
        ctx = action.get('context') or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {'uid': self.env.uid}) if ctx.strip() else {}
        if not isinstance(ctx, dict):
            ctx = {}
        ctx = dict(ctx)
        ctx.update(extra)
        return ctx

    def _ages_open_move_lines(self, name, domain):
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all')
        action['name'] = name
        action['domain'] = domain
        action['context'] = self._ages_merge_action_context(
            action, search_default_posted=1, create=False,
        )
        return action

    def _ages_open_moves(self, name, domain, xml_id=None):
        if xml_id:
            action = self.env['ir.actions.act_window']._for_xml_id(xml_id)
            action['name'] = name
            action['domain'] = domain
            action['context'] = self._ages_merge_action_context(action, create=False)
            return action
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            'context': {'create': False},
            'target': 'current',
        }

    @api.model
    def ages_open_overview_kpi(self, kpi):
        """Open the journal items / invoices that make up a dashboard KPI."""
        self.check_access_rights('read')
        company = self.env.company
        aml = self._ages_overview_aml_base()
        unpaid_states = ('not_paid', 'partial', 'in_payment')

        if kpi == 'revenue':
            return self._ages_open_move_lines(_('Revenue'), aml + [
                ('account_id.internal_group', '=', 'income'),
            ])
        if kpi == 'expenses':
            return self._ages_open_move_lines(_('Expenses'), aml + [
                ('account_id.internal_group', '=', 'expense'),
            ])
        if kpi == 'gross_margin':
            return self._ages_open_move_lines(_('Gross Margin'), aml + [
                '|',
                ('account_id.internal_group', '=', 'income'),
                ('account_id.account_type', '=', 'expense_direct_cost'),
            ])
        if kpi == 'net_margin':
            return self._ages_open_move_lines(_('Net Margin'), aml + [
                ('account_id.internal_group', 'in', ('income', 'expense')),
            ])
        if kpi == 'unpaid_customers':
            return self._ages_open_moves(
                _('Unpaid Customers'),
                [
                    ('company_id', '=', company.id),
                    ('state', '=', 'posted'),
                    ('move_type', 'in', ('out_invoice', 'out_refund', 'out_receipt')),
                    ('payment_state', 'in', unpaid_states),
                ],
                'account.action_move_out_invoice_type',
            )
        if kpi == 'unpaid_suppliers':
            return self._ages_open_moves(
                _('Unpaid Suppliers'),
                [
                    ('company_id', '=', company.id),
                    ('state', '=', 'posted'),
                    ('move_type', 'in', ('in_invoice', 'in_refund', 'in_receipt')),
                    ('payment_state', 'in', unpaid_states),
                ],
                'account.action_move_in_invoice_type',
            )
        if kpi == 'unpaid':
            return self._ages_open_moves(
                _('Unpaid Invoices & Bills'),
                [
                    ('company_id', '=', company.id),
                    ('state', '=', 'posted'),
                    ('move_type', 'in', (
                        'out_invoice', 'out_refund', 'out_receipt',
                        'in_invoice', 'in_refund', 'in_receipt',
                    )),
                    ('payment_state', 'in', unpaid_states),
                ],
            )
        if kpi == 'cash_in':
            return self._ages_open_move_lines(_('Cash In'), aml + [
                ('account_id.account_type', '=', 'asset_cash'),
                ('debit', '>', 0),
            ])
        if kpi == 'cash_out':
            return self._ages_open_move_lines(_('Cash Out'), aml + [
                ('account_id.account_type', '=', 'asset_cash'),
                ('credit', '>', 0),
            ])
        if kpi == 'cash_flow':
            return self._ages_open_move_lines(_('Cash Flow'), aml + [
                ('account_id.account_type', '=', 'asset_cash'),
            ])
        return False


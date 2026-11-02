# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardFinance(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_finance_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._capability_map().get('account') or not self._can_read('account.move.line'):
            return self._unavailable(scope, 'finance', 'Accounting access is required for this dashboard.')
        date_from, date_to = scope['date_from'], scope['date_to']
        prev_from, prev_to = scope['previous_from'], scope['previous_to']
        income_extra = [('account_id.account_type', 'in', ('income', 'income_other'))]
        expense_extra = [('account_id.account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))]
        cash_extra = [('account_id.account_type', '=', 'asset_cash')]

        revenue = self._aml_sum(scope, income_extra, date_from, date_to, invert=True)
        expenses = self._aml_sum(scope, expense_extra, date_from, date_to)
        prev_revenue = self._aml_sum(scope, income_extra, prev_from, prev_to, invert=True)
        prev_expenses = self._aml_sum(scope, expense_extra, prev_from, prev_to)
        cash_total = self._aml_sum(scope, cash_extra, None, date_to)
        bank_balance, cash_balance = self._cash_bank_snapshot(scope, date_to)
        inflow_domain = self._aml_posted_domain(scope, cash_extra + [('debit', '>', 0)]) + self._date_domain('date', date_from, date_to)
        outflow_domain = self._aml_posted_domain(scope, cash_extra + [('credit', '>', 0)]) + self._date_domain('date', date_from, date_to)
        inflow = self._read_group_sum('account.move.line', inflow_domain, 'debit')
        outflow = self._read_group_sum('account.move.line', outflow_domain, 'credit')

        ar_ap = self._snapshot_ar_ap(scope)
        rec_domain = ar_ap['rec_domain']
        pay_domain = ar_ap['pay_domain']
        receivables = ar_ap['receivables']
        payables = ar_ap['payables']
        aged_ar = ar_ap['aged_ar']
        aged_ap = ar_ap['aged_ap']
        today = fields.Date.context_today(self)
        grace = self._config_int('ages_enterprise_dashboard.overdue_grace_days', 0)
        overdue_cutoff = today - timedelta(days=grace) if grace else today
        overdue_ar = self._currency_sum('account.move', rec_domain + [
            ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', overdue_cutoff),
        ], 'amount_residual_signed', scope, date_field='date', company_currency=True)
        overdue_ap = abs(self._currency_sum('account.move', pay_domain + [
            ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', overdue_cutoff),
        ], 'amount_residual_signed', scope, date_field='date', company_currency=True))
        if self._has_field('account.move.line', 'ages_is_vendor_retention_line'):
            retention_residual = abs(self._currency_sum(
                'account.move.line',
                self._aml_posted_domain(scope, [
                    ('ages_is_vendor_retention_line', '=', True),
                    ('amount_residual', '!=', 0),
                ]),
                'amount_residual',
                scope,
                date_field='date',
                company_currency=True,
            ) or 0.0)
        else:
            retention_residual = 0.0

        invoice_amount = self._currency_sum(
            'account.move', rec_domain + self._date_domain('invoice_date', date_from, date_to),
            'amount_total_signed', scope, date_field='date', company_currency=True,
        )
        bill_amount = abs(self._currency_sum(
            'account.move', pay_domain + self._date_domain('invoice_date', date_from, date_to),
            'amount_total_signed', scope, date_field='date', company_currency=True,
        ))
        collections = self._payment_sum(scope, 'inbound', date_from, date_to)
        vendor_payments = self._payment_sum(scope, 'outbound', date_from, date_to)

        unposted_domain = self._scope_domain('account.move', scope, [('state', '=', 'draft')])
        unposted = self._search_count('account.move', unposted_domain)
        unposted_value = abs(self._currency_sum(
            'account.move', unposted_domain, 'amount_total_signed', scope,
            date_field='date', company_currency=True,
        ) or 0.0)

        unreconciled = unreconciled_value = 0
        if self._has_field('account.move.line', 'reconciled'):
            unrec_domain = self._aml_posted_domain(scope, [
                ('reconciled', '=', False),
                ('account_id.reconcile', '=', True),
                ('amount_residual', '!=', 0),
            ])
            unreconciled = self._search_count('account.move.line', unrec_domain)
            unreconciled_value = abs(self._currency_sum(
                'account.move.line', unrec_domain, 'amount_residual', scope,
                date_field='date', company_currency=True,
            ) or 0.0)

        pending_pay = pending_pay_value = 0
        if self._has_field('account.payment', 'validation_status'):
            pending_domain = self._scope_domain('account.payment', scope, [
                ('validation_status', 'in', ('waiting', 'pending')),
            ])
            pending_pay = self._search_count('account.payment', pending_domain)
            amount_field = 'amount_company_currency_signed' if self._has_field(
                'account.payment', 'amount_company_currency_signed'
            ) else 'amount'
            pending_pay_value = abs(self._currency_sum(
                'account.payment', pending_domain, amount_field, scope,
                date_field='date',
                company_currency=(amount_field == 'amount_company_currency_signed'),
            ) or 0.0)

        budget_planned = False
        budget_warning = 'Budget actual (practical_amount) is computed, not stored, so it is not aggregated here.'
        line_model = self._budget_line_model()
        if line_model and self._has_field(line_model, 'planned_amount'):
            budget_domain = [('crossovered_budget_state', 'in', ('confirm', 'validate', 'done'))] if self._has_field(
                line_model, 'crossovered_budget_state'
            ) else []
            if date_from and self._has_field(line_model, 'date_to'):
                budget_domain.append(('date_to', '>=', date_from))
            if date_to and self._has_field(line_model, 'date_from'):
                budget_domain.append(('date_from', '<=', date_to))
            budget_domain = self._scope_domain(line_model, scope, budget_domain)
            budget_planned = self._read_group_sum(line_model, budget_domain, 'planned_amount')
        else:
            budget_warning = 'No readable budget line model. Planned/actual variance is unavailable.'

        budget_rows, budget_totals, budget_actual_warning = self._budget_actual_rows(scope)
        if budget_actual_warning:
            budget_warning = budget_actual_warning
        elif budget_rows:
            budget_warning = 'Budget actual is shown from overlapping budget lines. Planned uses stored planned_amount.'

        main_summary = self._main_summary_payload(scope)

        kpis = [
            self._kpi(scope, 'revenue', 'Revenue', revenue, prev_revenue, 'aml_income',
                      'Posted income AML; inverted so income is positive.',
                      basis='flow', date_field='account.move.line.date',
                      formula='SUM(balance) of posted income AML, sign-inverted.'),
            self._kpi(scope, 'expenses', 'Expenses', expenses, prev_expenses, 'aml_expense',
                      'Posted expense AML balance.',
                      basis='flow', date_field='account.move.line.date',
                      formula='SUM(balance) of posted expense AML.'),
            self._kpi(scope, 'profit', 'Net result', revenue - expenses, prev_revenue - prev_expenses, False,
                      'Revenue minus expenses, same posted-AML basis.',
                      basis='flow', date_field='account.move.line.date',
                      formula='Revenue − expenses on posted AML.'),
            self._kpi(scope, 'cash', 'Cash & bank snapshot', cash_total, False, 'aml_cash_snapshot',
                      'Posted cash/bank AML through date_to.',
                      basis='snapshot', date_field='account.move.line.date',
                      formula='SUM(balance) asset_cash through date_to.'),
            self._kpi(scope, 'bank', 'Bank snapshot', bank_balance, False, 'aml_bank_snapshot',
                      'Posted asset_cash AML on bank journals through date_to.',
                      basis='snapshot', date_field='account.move.line.date',
                      formula='asset_cash AML on journals type=bank.'),
            self._kpi(scope, 'cash_in_hand', 'Cash snapshot', cash_balance, False, 'aml_cash_hand_snapshot',
                      'Posted asset_cash AML on cash journals through date_to.',
                      basis='snapshot', date_field='account.move.line.date',
                      formula='asset_cash AML on journals type=cash.'),
            self._kpi(scope, 'inflow', 'Cash inflow', inflow, False, 'cash_inflow',
                      'Debits on cash/bank accounts in period.',
                      basis='flow', date_field='account.move.line.date',
                      formula='SUM(debit) of posted asset_cash AML.'),
            self._kpi(scope, 'outflow', 'Cash outflow', outflow, False, 'cash_outflow',
                      'Credits on cash/bank accounts in period.',
                      basis='flow', date_field='account.move.line.date',
                      formula='SUM(credit) of posted asset_cash AML.'),
            self._kpi(scope, 'receivables', 'Receivables', receivables, ar_ap['previous_receivables'], 'customer_receivables',
                      'As-of AgedPartnerBalanceEngine total at date_to.' if ar_ap['ar_basis'] == 'aged_engine' else 'Live posted customer residual. Historical as-of aging uses AgedPartnerBalanceEngine when installed.',
                      basis='snapshot', date_field='account.move.invoice_date_due',
                      formula='AgedPartnerBalanceEngine total.' if ar_ap['ar_basis'] == 'aged_engine' else 'SUM(amount_residual_signed) posted customer invoices/refunds.'),
            self._kpi(scope, 'overdue_ar', 'Overdue receivables', overdue_ar, False, 'overdue_invoices',
                      'Posted unpaid/partial customer invoices with invoice_date_due before today minus grace days.',
                      basis='snapshot', date_field='account.move.invoice_date_due',
                      formula='Residual where payment_state in not_paid/partial and due < cutoff.'),
            self._kpi(scope, 'payables', 'Payables', payables, ar_ap['previous_payables'], 'vendor_payables',
                      'As-of AgedPartnerBalanceEngine total at date_to. Vendor retention lines stay on their GL.' if ar_ap['ap_basis'] == 'aged_engine' else 'Live posted vendor residual. Vendor retention lines stay on their GL.',
                      basis='snapshot', date_field='account.move.invoice_date_due',
                      formula='AgedPartnerBalanceEngine payable total.' if ar_ap['ap_basis'] == 'aged_engine' else 'ABS(SUM(amount_residual_signed)) posted vendor bills/refunds.'),
            self._kpi(scope, 'overdue_ap', 'Overdue payables', overdue_ap, False, 'overdue_bills',
                      'Posted unpaid/partial vendor bills past due. Retention residual is reported separately.',
                      basis='snapshot', date_field='account.move.invoice_date_due',
                      formula='ABS residual of unpaid/partial vendor bills due before cutoff.'),
            self._kpi(scope, 'retention_ap', 'Vendor retention residual', retention_residual, False, 'vendor_retention_lines',
                      'Open residual on AML flagged ages_is_vendor_retention_line. Not ordinary currently payable.',
                      basis='snapshot', date_field='account.move.line.date',
                      formula='ABS(SUM(amount_residual)) where ages_is_vendor_retention_line.'),
            self._kpi(scope, 'invoices', 'Customer invoices', invoice_amount, False, 'customer_invoices',
                      'Posted customer invoice/refund totals in the selected invoice_date range.',
                      basis='flow', date_field='account.move.invoice_date',
                      formula='SUM(amount_total_signed) posted customer invoices.'),
            self._kpi(scope, 'bills', 'Vendor bills', bill_amount, False, 'vendor_bills',
                      'Posted vendor bill/refund totals in the selected invoice_date range.',
                      basis='flow', date_field='account.move.invoice_date',
                      formula='ABS(SUM(amount_total_signed)) posted vendor bills.'),
            self._kpi(scope, 'collections', 'Customer collections', collections, False, 'customer_collections',
                      'Posted/in-process inbound payments, excluding internal transfers.',
                      basis='flow', date_field='account.payment.date',
                      formula='ABS(SUM(amount_company_currency_signed)) inbound paid/in_process.'),
            self._kpi(scope, 'vendor_payments', 'Vendor payments', vendor_payments, False, 'vendor_payments',
                      'Posted/in-process outbound payments, excluding internal transfers.',
                      basis='flow', date_field='account.payment.date',
                      formula='ABS(SUM(amount_company_currency_signed)) outbound paid/in_process.'),
            self._kpi(scope, 'unposted', 'Unposted moves', unposted, False, 'unposted_moves',
                      'Draft account.move count in scope.',
                      suffix='', basis='count', date_field='', formula='COUNT draft account.move.'),
            self._kpi(scope, 'unposted_value', 'Unposted move value', unposted_value, False, 'unposted_moves',
                      'ABS of draft move amount_total_signed. Drafts are not accounting actuals.',
                      basis='count', date_field='', formula='ABS(SUM(amount_total_signed)) draft moves.'),
            self._kpi(scope, 'unreconciled', 'Unreconciled items', unreconciled, False, 'unreconciled',
                      'Posted reconcile-able AML with a non-zero residual.',
                      suffix='', basis='count', date_field='account.move.line.date',
                      formula='COUNT posted AML reconciled=False and amount_residual != 0.'),
            self._kpi(scope, 'unreconciled_value', 'Unreconciled residual', unreconciled_value, False, 'unreconciled',
                      'ABS residual of unreconciled posted AML.',
                      basis='snapshot', date_field='account.move.line.date',
                      formula='ABS(SUM(amount_residual)) unreconciled posted AML.'),
            self._kpi(scope, 'pending_pay', 'Payments pending approval', pending_pay, False, 'pending_payments',
                      'Payments whose validation_status is waiting or pending.',
                      suffix='', basis='count', date_field='account.payment.date',
                      formula='COUNT account.payment validation_status in waiting/pending.'),
            self._kpi(scope, 'pending_pay_value', 'Pending payment value', pending_pay_value, False, 'pending_payments',
                      'Company-currency signed amount of payments waiting approval.',
                      basis='count', date_field='account.payment.date',
                      formula='ABS(SUM(amount_company_currency_signed)) pending payments.'),
        ]
        unassigned_rev = self._unassigned_analytic_amount(scope, income_extra, date_from, date_to, invert=True)
        unassigned_exp = self._unassigned_analytic_amount(scope, expense_extra, date_from, date_to)
        kpis.append(self._kpi(
            scope, 'unassigned_analytic', 'Unassigned analytic amount', unassigned_rev + unassigned_exp, False, 'aml_expense',
            'Posted income+expense AML in the period with empty analytic_distribution.',
            basis='flow', date_field='account.move.line.date',
            formula='ABS(SUM(balance)) posted P&L AML where analytic_distribution is empty.',
        ))
        kpis.append(self._kpi(
            scope, 'unassigned_rev', 'Unassigned analytic income', unassigned_rev, False, 'aml_income',
            'Posted income AML with empty analytic_distribution.',
            basis='flow', date_field='account.move.line.date',
        ))
        kpis.append(self._kpi(
            scope, 'unassigned_exp', 'Unassigned analytic expense', unassigned_exp, False, 'aml_expense',
            'Posted expense AML with empty analytic_distribution.',
            basis='flow', date_field='account.move.line.date',
        ))
        if budget_planned is not False:
            kpis.append(self._kpi(
                scope, 'budget_planned', 'Budget planned', budget_planned or 0.0, False, 'budgets',
                'Stored planned_amount on confirmed/validated/done budget lines overlapping the period.',
                basis='plan', date_field='crossovered.budget.lines.date_from',
                formula='SUM(planned_amount) overlapping budget lines.',
            ))
        if budget_rows:
            kpis.append(self._kpi(
                scope, 'budget_actual', 'Budget actual (browsed lines)', budget_totals.get('actual') or 0.0, False, 'budgets',
                'Computed practical_amount on browsed overlapping budget lines. Not a SQL aggregate.',
                basis='plan',
            ))
            kpis.append(self._kpi(
                scope, 'budget_variance', 'Budget planned − actual (browsed)', budget_totals.get('variance') or 0.0, False, 'budgets',
                'Difference of stored planned_amount and browsed practical_amount on the visible line set.',
                basis='plan',
            ))
        working_capital = (cash_total or 0.0) + (receivables or 0.0) - (payables or 0.0)
        kpis.append(self._kpi(
            scope, 'working_capital', 'Cash + AR − AP', working_capital, False, False,
            'Snapshot cash/bank plus posted customer residual minus posted vendor residual. Not a complete balance-sheet working-capital figure.',
            basis='snapshot',
        ))
        period_days = max(((date_to - date_from).days + 1) if date_from and date_to else 0, 1)
        if invoice_amount:
            kpis.append(self._kpi(
                scope, 'dso', 'Receivable days (invoice basis)',
                (receivables or 0.0) / abs(invoice_amount) * period_days,
                False, 'customer_receivables',
                'Open residual / period posted customer invoice total × days in period. Not a collections forecast.',
                suffix='', basis='ratio', kind='count',
            ))
        else:
            kpis.append(self._unavailable_kpi(
                scope, 'dso', 'Receivable days (invoice basis)',
                'No posted customer invoices in the period, so the denominator is empty.',
            ))
        if bill_amount:
            kpis.append(self._kpi(
                scope, 'dpo', 'Payable days (bill basis)',
                (payables or 0.0) / abs(bill_amount) * period_days,
                False, 'vendor_payables',
                'Open vendor residual / period posted vendor bill total × days in period.',
                suffix='', basis='ratio', kind='count',
            ))
        else:
            kpis.append(self._unavailable_kpi(
                scope, 'dpo', 'Payable days (bill basis)',
                'No posted vendor bills in the period, so the denominator is empty.',
            ))
        pnl_engine = self._profit_loss_payload(scope)
        if pnl_engine:
            net_line = next(
                (line for line in pnl_engine.get('flat') or [] if line.get('id') in ('NP', 'NET', 'net_profit') or line.get('line_type') == 'total'),
                {},
            )
            if net_line:
                kpis.append(self._kpi(
                    scope, 'engine_pnl', 'Engine net result', net_line.get('balance') or 0.0, False, 'aml_income',
                    'ProfitLossEngine posted P&L. Dashboard revenue/expense KPIs remain the account_type AML sums.',
                    basis='flow', date_field='account.move.line.date',
                ))
        if main_summary and main_summary.get('kpis'):
            ms = main_summary['kpis']
            kpis.extend([
                self._kpi(scope, 'ms_opening', 'Main Summary opening', ms.get('opening') or 0.0, False, 'aml_cash',
                          'Cash-basis opening from MainSummaryEngine. Not P&L revenue.',
                          basis='cash', date_field='account.move.line.date',
                          formula='MainSummaryEngine opening on posted cash/bank AML.'),
                self._kpi(scope, 'ms_received', 'Main Summary received', ms.get('received') or 0.0, False, 'aml_cash',
                          'Cash-basis receipts from MainSummaryEngine.',
                          basis='cash', date_field='account.move.line.date',
                          formula='MainSummaryEngine received.'),
                self._kpi(scope, 'ms_expenses', 'Main Summary cash out', ms.get('expenses') or 0.0, False, 'aml_cash',
                          'Cash-basis expenses from MainSummaryEngine. Not accounting P&L expense.',
                          basis='cash', date_field='account.move.line.date',
                          formula='MainSummaryEngine expenses.'),
                self._kpi(scope, 'ms_transfers', 'Main Summary transfers', ms.get('transfers') or 0.0, False, 'aml_cash',
                          'Cash-basis transfers from MainSummaryEngine.',
                          basis='cash', date_field='account.move.line.date',
                          formula='MainSummaryEngine transfers.'),
                self._kpi(scope, 'ms_closing', 'Main Summary closing', ms.get('closing') or 0.0, False, 'aml_cash',
                          'Cash-basis closing from MainSummaryEngine.',
                          basis='cash', date_field='account.move.line.date',
                          formula='MainSummaryEngine closing.'),
            ])

        labels, revenue_trend = self._monthly_aml_trend(scope, income_extra, invert=True)
        _labels, expense_trend = self._monthly_aml_trend(scope, expense_extra)
        income_rows = self._account_rank(
            scope, income_extra, date_from, date_to, invert=True, action_key='aml_income'
        )
        expense_rows = self._account_rank(
            scope, expense_extra, date_from, date_to, action_key='aml_expense'
        )
        sub_income = self._aml_grouped(scope, income_extra, date_from, date_to, 'move_id.ages_sub_company_id', invert=True)
        sub_expense = self._aml_grouped(scope, expense_extra, date_from, date_to, 'move_id.ages_sub_company_id')
        project_income = self._aml_grouped(scope, income_extra, date_from, date_to, 'move_id.ages_project_id', invert=True)
        project_expense = self._aml_grouped(scope, expense_extra, date_from, date_to, 'move_id.ages_project_id')
        analytic_income = self._analytic_project_rows(scope, income_extra, date_from, date_to, invert=True, limit=12)
        analytic_expense = self._analytic_project_rows(scope, expense_extra, date_from, date_to, limit=12)
        live_aging = self._aging_two_bucket(scope)
        ar_labels = aged_ar['labels'] if aged_ar else live_aging['labels']
        ar_values = aged_ar['values'] if aged_ar else live_aging['ar']
        ap_labels = aged_ap['labels'] if aged_ap else live_aging['labels']
        ap_values = aged_ap['values'] if aged_ap else live_aging['ap']
        invoice_trend = self._move_monthly(scope, rec_domain, 'invoice_date', 'amount_total_signed')
        payment_trend = self._payment_monthly(scope, payment_type='inbound')
        bill_trend = self._move_monthly(scope, pay_domain, 'invoice_date', 'amount_total_signed')
        vendor_pay_trend = self._payment_monthly(scope, payment_type='outbound')

        charts = {
            'pnl': self._chart('mixed', 'Monthly P&L', labels, [
                {'label': 'Revenue', 'data': revenue_trend, 'type': 'bar'},
                {'label': 'Expenses', 'data': expense_trend, 'type': 'bar'},
                {'label': 'Result', 'data': [round(rev - exp, 2) for rev, exp in zip(revenue_trend, expense_trend)], 'type': 'line'},
            ], unit='money', size='lg', allow_toggle=True, why_key='revenue'),
            'income_accounts': self._chart('doughnut', 'Income by account', [r['name'] for r in income_rows], [
                {'label': 'Income', 'data': [r['amount'] for r in income_rows]},
            ]),
            'expense_accounts': self._chart('doughnut', 'Expenses by account', [r['name'] for r in expense_rows], [
                {'label': 'Expenses', 'data': [r['amount'] for r in expense_rows]},
            ]),
            'sub_company': self._chart('bar', 'Income / expense by active company', [r['name'] for r in sub_income or sub_expense], [
                {'label': 'Income', 'data': [r['amount'] for r in sub_income]},
                {'label': 'Expenses', 'data': [next((x['amount'] for x in sub_expense if x['name'] == r['name']), 0.0) for r in sub_income] if sub_income else [r['amount'] for r in sub_expense]},
            ]) if (sub_income or sub_expense) else self._chart('bar', 'Income / expense by active company', [], []),
            'projects': self._chart('bar', 'Recorded income by project', [r['name'] for r in project_income], [
                {'label': 'Income', 'data': [r['amount'] for r in project_income]},
            ]),
            'project_cost': self._chart('bar', 'Recorded expense by project header', [r['name'] for r in project_expense], [
                {'label': 'Expenses', 'data': [r['amount'] for r in project_expense]},
            ]),
            'analytic': self._chart('bar', 'Income / expense by analytic project', [r['name'] for r in analytic_income or analytic_expense], [
                {'label': 'Income', 'data': [r['amount'] for r in analytic_income]},
                {'label': 'Expenses', 'data': [
                    next((item['amount'] for item in analytic_expense if item['res_id'] == row['res_id']), 0.0)
                    for row in analytic_income
                ] if analytic_income else [r['amount'] for r in analytic_expense]},
            ], action_key='projects', group_field='id', label_ids=[r.get('res_id') for r in analytic_income or analytic_expense]) if (analytic_income or analytic_expense) else self._chart('bar', 'Income / expense by analytic project', [], []),
            'aging_ar': self._aging_chart(
                'Receivable aging (as-of)' if aged_ar else 'Receivable aging (overdue vs not due)',
                ar_labels, ar_values, 'Receivables', bool(aged_ar),
            ),
            'aging_ap': self._aging_chart(
                'Payable aging (as-of)' if aged_ap else 'Payable aging (overdue vs not due)',
                ap_labels, ap_values, 'Payables', bool(aged_ap),
            ),
            'invoice_payment': self._chart('mixed', 'Invoices vs collections', invoice_trend[0], [
                {'label': 'Customer invoices', 'data': invoice_trend[1], 'type': 'bar'},
                {'label': 'Collections', 'data': payment_trend[1], 'type': 'line'},
            ], unit='money', size='md', allow_toggle=True),
            'vendor_invoice_payment': self._chart('mixed', 'Vendor bills vs vendor payments', bill_trend[0], [
                {'label': 'Vendor bills', 'data': bill_trend[1], 'type': 'bar'},
                {'label': 'Vendor payments', 'data': vendor_pay_trend[1], 'type': 'line'},
            ], unit='money', size='md', allow_toggle=True),
            'cashflow': self._chart('area', 'Cash inflow vs outflow vs net', *self._cash_flow_trend(scope), unit='money', size='lg', allow_toggle=True),
            'journals': self._journal_balance_chart(scope, date_to),
        }
        if budget_planned is not False:
            charts['budget'] = self._chart('bar', 'Budget planned vs browsed actual', ['Planned', 'Actual'], [
                {'label': 'Amount', 'data': [
                    round(budget_planned or 0.0, 2),
                    round((budget_totals or {}).get('actual') or 0.0, 2),
                ]},
            ])
        if pnl_engine:
            top_pnl = [
                line for line in pnl_engine.get('flat') or []
                if line.get('level', 0) <= 1
            ][:8]
            charts['engine_pnl'] = self._chart(
                'bar', 'Profit & Loss engine structure',
                [line.get('name') for line in top_pnl],
                [{'label': 'Balance', 'data': [round(line.get('balance') or 0.0, 2) for line in top_pnl]}],
            )

        tables = {
            'income_accounts': self._mgmt_table('Largest income accounts', [
                {'key': 'name', 'label': 'Account'}, {'key': 'formatted', 'label': 'Amount'},
            ], income_rows, 'aml_income'),
            'expense_accounts': self._mgmt_table('Largest expense accounts', [
                {'key': 'name', 'label': 'Account'}, {'key': 'formatted', 'label': 'Amount'},
            ], expense_rows, 'aml_expense'),
            'overdue_ar_partners': self._overdue_partner_table(scope, 'out_invoice', 'Overdue receivables by customer', 'overdue_invoices'),
            'overdue_ap_partners': self._overdue_partner_table(scope, 'in_invoice', 'Overdue payables by vendor', 'overdue_bills'),
            'overdue_ar_invoices': self._overdue_invoice_table(scope, 'out_invoice', 'Overdue customer invoices', 'overdue_invoices', overdue_cutoff),
            'overdue_ap_invoices': self._overdue_invoice_table(scope, 'in_invoice', 'Overdue vendor bills', 'overdue_bills', overdue_cutoff),
            'journals': self._cash_journal_table(scope, date_to),
            'unposted': self._move_table(scope, unposted_domain, 'Unposted journal entries', 'unposted_moves'),
            'pending_payments': self._pending_payment_table(scope),
            'project_pnl': self._project_pnl_table(scope, project_income, project_expense),
            'sub_company_pnl': self._mgmt_table('Active-company recorded income', [
                {'key': 'name', 'label': 'Active company'}, {'key': 'formatted', 'label': 'Income'},
            ], sub_income, 'aml_income'),
        }
        if budget_rows:
            tables['budget_lines'] = self._mgmt_table('Budget planned vs actual (browsed lines)', [
                {'key': 'name', 'label': 'Line'},
                {'key': 'planned', 'label': 'Planned'},
                {'key': 'actual', 'label': 'Actual'},
                {'key': 'variance', 'label': 'Variance'},
            ], budget_rows, 'budgets')
        if pnl_engine:
            tables['engine_pnl'] = self._mgmt_table('Profit & Loss engine', [
                {'key': 'name', 'label': 'Line'}, {'key': 'amount', 'label': 'Balance'},
            ], [{
                'name': line.get('name'),
                'amount': self._format_money(line.get('balance') or 0.0, scope),
            } for line in (pnl_engine.get('flat') or [])[:25]], 'aml_income')
        if main_summary:
            centres = [row for row in (main_summary.get('cost_centres') or []) if row.get('line_type') != 'total'][:15]
            tables['main_summary'] = self._mgmt_table('Main Summary cost centres', [
                {'key': 'name', 'label': 'Centre'},
                {'key': 'opening', 'label': 'Opening'},
                {'key': 'received', 'label': 'Received'},
                {'key': 'expenses', 'label': 'Cash out'},
                {'key': 'closing', 'label': 'Closing'},
            ], [{
                'name': row.get('name') or 'Unassigned',
                'opening': self._format_money(row.get('opening') or 0.0, scope),
                'received': self._format_money(row.get('received') or 0.0, scope),
                'expenses': self._format_money(row.get('expenses') or 0.0, scope),
                'closing': self._format_money(row.get('closing') or 0.0, scope),
            } for row in centres], 'aml_cash')
            banks = [row for row in (main_summary.get('banks') or []) if row.get('journal_type') in ('bank', 'cash')][:15]
            tables['main_summary_banks'] = self._mgmt_table('Main Summary banks and cash', [
                {'key': 'name', 'label': 'Journal'},
                {'key': 'type', 'label': 'Type'},
                {'key': 'closing', 'label': 'Closing'},
            ], [{
                'name': row.get('name') or '',
                'type': row.get('journal_type') or '',
                'closing': self._format_money(row.get('closing') or 0.0, scope),
            } for row in banks], 'aml_cash')
            site_rows = [row for row in (main_summary.get('cash_at_site') or []) if row.get('line_type') != 'total'][:15]
            if site_rows:
                tables['main_summary_site'] = self._mgmt_table('Main Summary cash at site', [
                    {'key': 'name', 'label': 'Centre'},
                    {'key': 'closing', 'label': 'Closing'},
                ], [{
                    'name': row.get('name') or 'Unassigned',
                    'closing': self._format_money(row.get('closing') or row.get('balance') or 0.0, scope),
                } for row in site_rows], 'aml_cash')

        coverage = self._analytic_coverage(scope, date_from, date_to)
        warnings = []
        if coverage is not False and coverage < 100:
            warnings.append('Posted journal items with analytic distribution: %s%%.' % coverage)
        if aged_ar:
            warnings.append('Receivable aging is as-of %s from AgedPartnerBalanceEngine, not live amount_residual.' % aged_ar.get('date_label'))
        else:
            warnings.append('As-of receivable aging is unavailable (ages_custom_reports not importable). Live invoice residual is shown instead.')
        if aged_ap:
            warnings.append('Payable aging is as-of %s from AgedPartnerBalanceEngine.' % aged_ap.get('date_label'))
        if not main_summary:
            warnings.append('Main Summary cash waterfall is unavailable because MainSummaryEngine could not be imported from ages_main_summary.')
        else:
            warnings.append('Main Summary opening/received/cash-out/closing uses MainSummaryEngine formulas, not a reimplemented cash waterfall.')
        followup_table = self._followup_partner_table(scope)
        if followup_table:
            tables['followup'] = followup_table
        warnings.append(budget_warning)
        if grace:
            warnings.append('Overdue uses a configured grace of %s day(s).' % grace)
        self._attach_sparklines(kpis, {
            'revenue': (charts.get('pnl'), 0, 'money'),
            'expenses': (charts.get('pnl'), 1, 'money'),
            'profit': (charts.get('pnl'), 2, 'money'),
            'inflow': (charts.get('cashflow'), 0, 'money'),
            'outflow': (charts.get('cashflow'), 1, 'money'),
        })
        return self._payload(
            scope, 'finance', kpis, charts, tables,
            date_field='account.move.line.date', warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['revenue', 'expenses', 'profit', 'engine_pnl'] if any(kpi.get('key') == 'engine_pnl' for kpi in kpis) else ['revenue', 'expenses', 'profit', 'cash'],
                charts=[
                    ('pnl', 12),
                    self._layout_section(
                        'cash_kpis', 'kpis',
                        ['cash', 'bank', 'cash_in_hand', 'inflow', 'outflow', 'ms_opening', 'ms_received', 'ms_expenses', 'ms_closing'],
                        12, title='Cash',
                    ),
                    ('cashflow', 8), ('journals', 4),
                    self._layout_section(
                        'wc_kpis', 'kpis',
                        ['receivables', 'overdue_ar', 'payables', 'overdue_ap', 'retention_ap', 'working_capital'],
                        12, title='Working capital',
                    ),
                    ('aging_ar', 6), ('aging_ap', 6),
                    ('invoice_payment', 6), ('vendor_invoice_payment', 6),
                    ('analytic', 12),
                ],
                tables=['overdue_invoices', 'overdue_bills', 'journals', 'pending_payments'],
                more=['dso', 'dpo', 'revenue_runrate'],
            )},
        )

    def _account_rank(self, scope, extra, date_from, date_to, invert=False, limit=8, action_key=False):
        domain = self._aml_posted_domain(scope, extra) + self._date_domain('date', date_from, date_to)
        rows = self.env['account.move.line'].read_group(domain, ['balance:sum'], ['account_id'], lazy=False)
        ranked = []
        for group in rows:
            account = group.get('account_id')
            amount = group.get('balance') or 0.0
            if invert:
                amount = -amount
            ranked.append({
                'name': account[1] if account else 'Unknown',
                'amount': abs(amount),
                'formatted': self._format_money(abs(amount), scope),
                'res_id': account[0] if account else False,
                'res_field': 'account_id',
                'action_key': action_key,
            })
        ranked.sort(key=lambda item: item['amount'], reverse=True)
        return ranked[:limit]

    def _aging_buckets(self, scope):
        return self._aging_two_bucket(scope)

    def _aging_two_bucket(self, scope):
        labels = ['Overdue', 'Not due']
        ar = [0.0, 0.0]
        ap = [0.0, 0.0]
        if not self._can_read('account.move'):
            return {'labels': labels, 'ar': ar, 'ap': ap}
        today = fields.Date.context_today(self)
        grace = self._config_int('ages_enterprise_dashboard.overdue_grace_days', 0)
        cutoff = today - timedelta(days=grace) if grace else today
        rec_overdue = self._currency_sum('account.move', self._scope_domain('account.move', scope, [
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', cutoff),
        ]), 'amount_residual_signed', scope, date_field='date', company_currency=True)
        rec_open = self._currency_sum('account.move', self._scope_domain('account.move', scope, [
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ]), 'amount_residual_signed', scope, date_field='date', company_currency=True)
        pay_overdue = abs(self._currency_sum('account.move', self._scope_domain('account.move', scope, [
            ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', cutoff),
        ]), 'amount_residual_signed', scope, date_field='date', company_currency=True))
        pay_open = abs(self._currency_sum('account.move', self._scope_domain('account.move', scope, [
            ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ]), 'amount_residual_signed', scope, date_field='date', company_currency=True))
        return {
            'labels': labels,
            'ar': [round(rec_overdue or 0.0, 2), round(max((rec_open or 0.0) - (rec_overdue or 0.0), 0.0), 2)],
            'ap': [round(pay_overdue or 0.0, 2), round(max((pay_open or 0.0) - (pay_overdue or 0.0), 0.0), 2)],
        }

    def _aging_chart(self, title, labels, values, series_label, engine=False):
        chart = self._chart('bar', title, labels, [{'label': series_label, 'data': values}], unit='money', size='md')
        tones = ['muted', 'warning', 'warning', 'danger', 'danger'] if engine else ['danger', 'muted']
        chart['heatstrip'] = [
            {'label': labels[index], 'value': values[index], 'tone': tones[index] if index < len(tones) else 'muted'}
            for index in range(len(labels))
        ]
        return chart

    def _cash_journal_table(self, scope, date_to):
        if not self._can_read('account.journal') or not self._can_read('account.move.line'):
            return self._mgmt_table('Cash and bank journals', [], [])
        journals = self.env['account.journal'].search([
            ('type', 'in', ('cash', 'bank')),
            ('company_id', 'in', [cid for cid in scope['company_ids'] if cid] or self.env.companies.ids),
        ])
        rows = []
        for journal in journals:
            domain = self._aml_posted_domain(scope, [
                ('account_id.account_type', '=', 'asset_cash'),
                ('journal_id', '=', journal.id),
                ('date', '<=', date_to),
            ])
            balance = self._read_group_sum('account.move.line', domain, 'balance')
            rows.append({
                'name': journal.display_name,
                'type': journal.type,
                'formatted': self._format_money(balance, scope),
                'formatted_raw': balance or 0.0,
                'res_id': journal.id,
                'res_field': 'journal_id',
                'action_key': 'aml_cash_snapshot',
            })
        return self._mgmt_table('Cash and bank journals', [
            {'key': 'name', 'label': 'Journal'},
            {'key': 'type', 'label': 'Type'},
            {'key': 'formatted', 'label': 'Balance'},
        ], rows, 'aml_cash')

    def _journal_balance_chart(self, scope, date_to):
        table = self._cash_journal_table(scope, date_to)
        rows = table.get('rows') or []
        return self._chart(
            'horizontalBar', 'Cash / bank composition by journal',
            [row.get('name') for row in rows],
            [{'label': 'Balance', 'data': [round(abs(row.get('formatted_raw') or 0.0), 2) for row in rows]}],
            unit='money', size='md', action_key='aml_cash_snapshot',
            group_field='journal_id', label_ids=[row.get('res_id') for row in rows],
        )

    def _project_pnl_table(self, scope, income_rows, expense_rows):
        names = []
        seen = set()
        for row in list(income_rows or []) + list(expense_rows or []):
            name = row.get('name') or 'Unassigned'
            if name not in seen:
                seen.add(name)
                names.append(name)
        table_rows = []
        for name in names:
            income_row = next((row for row in income_rows if row.get('name') == name), {})
            expense_row = next((row for row in expense_rows if row.get('name') == name), {})
            income = income_row.get('amount') or 0.0
            expense = expense_row.get('amount') or 0.0
            analytic_id = (
                income_row.get('analytic_account_id')
                or expense_row.get('analytic_account_id')
            )
            table_rows.append({
                'name': name,
                'income': self._format_money(income, scope),
                'expense': self._format_money(expense, scope),
                'margin': self._format_money(income - expense, scope),
                'res_value': [analytic_id] if analytic_id else False,
                'res_field': 'analytic_distribution',
                'res_operator': 'in',
                'action_key': 'aml_income' if analytic_id else False,
            })
        return self._mgmt_table('Project recorded financial summary', [
            {'key': 'name', 'label': 'Project'},
            {'key': 'income', 'label': 'Income'},
            {'key': 'expense', 'label': 'Expense'},
            {'key': 'margin', 'label': 'Recorded margin'},
        ], table_rows, 'aml_income')

    def _overdue_invoice_table(self, scope, move_type, title, action_key, cutoff):
        if not self._can_read('account.move'):
            return self._mgmt_table(title, [], [], action_key)
        records = self._search_read(
            'account.move',
            self._scope_domain('account.move', scope, [
                ('move_type', '=', move_type),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', cutoff),
            ]),
            ['name', 'partner_id', 'invoice_date_due', 'amount_residual_signed', 'payment_state'],
            limit=20,
            order='invoice_date_due, id',
        )
        rows = []
        for rec in records:
            partner = rec.get('partner_id')
            rows.append({
                'name': rec.get('name'),
                'partner': partner[1] if partner else '',
                'due': self._format_date(rec.get('invoice_date_due')),
                'state': rec.get('payment_state') or '',
                'residual': self._format_money(abs(rec.get('amount_residual_signed') or 0.0), scope),
                'res_id': rec.get('id'),
                'action_key': action_key,
            })
        return self._mgmt_table(title, [
            {'key': 'name', 'label': 'Document'},
            {'key': 'partner', 'label': 'Partner'},
            {'key': 'due', 'label': 'Due'},
            {'key': 'state', 'label': 'Payment'},
            {'key': 'residual', 'label': 'Residual'},
        ], rows, action_key)

    def _move_table(self, scope, domain, title, action_key):
        records = self._search_read(
            'account.move', domain,
            ['name', 'date', 'move_type', 'state', 'amount_total_signed', 'partner_id'],
            limit=20, order='date desc, id desc',
        )
        rows = []
        for rec in records:
            partner = rec.get('partner_id')
            rows.append({
                'name': rec.get('name'),
                'date': self._format_date(rec.get('date')),
                'partner': partner[1] if partner else '',
                'type': rec.get('move_type') or '',
                'amount': self._format_money(abs(rec.get('amount_total_signed') or 0.0), scope),
                'res_id': rec.get('id'),
                'action_key': action_key,
            })
        return self._mgmt_table(title, [
            {'key': 'name', 'label': 'Move'},
            {'key': 'date', 'label': 'Date'},
            {'key': 'partner', 'label': 'Partner'},
            {'key': 'type', 'label': 'Type'},
            {'key': 'amount', 'label': 'Total'},
        ], rows, action_key)

    def _pending_payment_table(self, scope):
        if not self._has_field('account.payment', 'validation_status'):
            return self._mgmt_table('Pending payment approvals', [], [], 'pending_payments',
                               empty='Payment validation_status is not present.')
        records = self._search_read(
            'account.payment',
            self._scope_domain('account.payment', scope, [('validation_status', 'in', ('waiting', 'pending'))]),
            ['name', 'date', 'partner_id', 'amount', 'validation_status', 'payment_type'],
            limit=20, order='date, id',
        )
        rows = []
        for rec in records:
            partner = rec.get('partner_id')
            rows.append({
                'name': rec.get('name'),
                'date': self._format_date(rec.get('date')),
                'partner': partner[1] if partner else '',
                'type': rec.get('payment_type') or '',
                'status': rec.get('validation_status') or '',
                'amount': self._format_money(rec.get('amount') or 0.0, scope),
                'res_id': rec.get('id'),
                'action_key': 'pending_payments',
            })
        return self._mgmt_table('Pending payment approvals', [
            {'key': 'name', 'label': 'Payment'},
            {'key': 'date', 'label': 'Date'},
            {'key': 'partner', 'label': 'Partner'},
            {'key': 'type', 'label': 'Type'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'amount', 'label': 'Amount'},
        ], rows, 'pending_payments')

    def _move_monthly(self, scope, base_domain, date_field, amount_field, months=6):
        from datetime import timedelta
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        cursor = date_to.replace(day=1)
        buckets = []
        for _index in range(months):
            buckets.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        buckets.reverse()
        labels, values = [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            domain = list(base_domain) + self._date_domain(date_field, month_start, month_end)
            values.append(round(abs(self._read_group_sum('account.move', domain, amount_field) or 0.0), 2))
        return labels, values

    def _payment_monthly(self, scope, months=6, payment_type='inbound'):
        from datetime import timedelta
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        cursor = date_to.replace(day=1)
        buckets = []
        for _index in range(months):
            buckets.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        buckets.reverse()
        labels, values = [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            values.append(round(self._payment_sum(scope, payment_type, month_start, month_end), 2))
        return labels, values

    def _followup_partner_table(self, scope):
        if not self._has_field('res.partner', 'payment_next_action_date'):
            return False
        today = fields.Date.context_today(self)
        domain = self._scope_domain('res.partner', scope, [
            ('payment_next_action_date', '!=', False),
            ('payment_next_action_date', '<=', today),
        ])
        fields_list = ['name', 'payment_next_action_date']
        if self._has_field('res.partner', 'payment_next_action'):
            fields_list.append('payment_next_action')
        records = self._search_read(
            'res.partner', domain, fields_list, limit=20, order='payment_next_action_date, id',
        )
        rows = []
        for rec in records:
            rows.append({
                'name': rec.get('name') or '',
                'due': self._format_date(rec.get('payment_next_action_date')),
                'action': rec.get('payment_next_action') or '',
                'res_id': rec.get('id'),
                'action_key': 'followup_partners',
            })
        return self._mgmt_table(
            'Follow-up next actions due',
            [
                {'key': 'name', 'label': 'Partner'},
                {'key': 'due', 'label': 'Next action date'},
                {'key': 'action', 'label': 'Stored next action'},
            ],
            rows,
            'followup_partners',
            empty='No partners with a stored payment_next_action_date on or before today.',
        )

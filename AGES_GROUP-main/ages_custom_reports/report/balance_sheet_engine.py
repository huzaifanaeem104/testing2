# -*- coding: utf-8 -*-

from .financial_report_engine import FinancialReportEngine, P_AND_L_ACCOUNT_TYPES
from .balance_sheet_structure import BALANCE_SHEET_STRUCTURE


class BalanceSheetEngine(FinancialReportEngine):
    """Compute hierarchical balance sheet lines (Enterprise-style grouping)."""

    report_structure = BALANCE_SHEET_STRUCTURE
    date_label_fields = ('date_to',)

    def _compute_expression(self, expression):
        if expression == 'curr_year_earnings':
            return self._compute_curr_year_earnings()
        if expression == 'prev_year_earnings':
            curr = self._balances.get('CURR_YEAR_EARNINGS')
            if curr is None:
                curr = self._compute_curr_year_earnings()
                self._balances['CURR_YEAR_EARNINGS'] = curr
            return self._compute_prev_year_earnings(curr)
        if expression == 'prev_retained_earnings':
            curr = self._balances.get('CURR_RETAINED_EARNINGS')
            if curr is None:
                _, accounts = self._sum_domain(
                    [('account_id.account_type', '=', 'equity')],
                    sign=-1,
                    date_scope='from_fiscalyear',
                    groupby_account=True,
                )
                curr = sum(a['balance'] for a in accounts)
                self._balances['CURR_RETAINED_EARNINGS'] = curr
            return self._compute_prev_retained_earnings(curr)
        return 0.0

    def _compute_curr_year_earnings(self):
        pnl_domain = [('account_id.account_type', 'in', P_AND_L_ACCOUNT_TYPES)]
        pnl, _ = self._sum_domain(pnl_domain, sign=-1, date_scope='from_fiscalyear')
        alloc_domain = [('account_id.account_type', '=', 'equity_unaffected')]
        alloc, _ = self._sum_domain(alloc_domain, sign=-1, date_scope='from_fiscalyear')
        return pnl + alloc

    def _compute_prev_year_earnings(self, curr_year_balance):
        pnl_domain = [('account_id.account_type', 'in', P_AND_L_ACCOUNT_TYPES)]
        pnl_total, _ = self._sum_domain(pnl_domain, sign=-1, date_scope='from_beginning')
        alloc_domain = [('account_id.account_type', '=', 'equity_unaffected')]
        alloc_total, _ = self._sum_domain(alloc_domain, sign=-1, date_scope='from_beginning')
        return pnl_total + alloc_total - curr_year_balance

    def _compute_prev_retained_earnings(self, curr_retained_balance):
        total, _ = self._sum_domain(
            [('account_id.account_type', '=', 'equity')],
            sign=-1,
            date_scope='to_date',
        )
        return total - curr_retained_balance

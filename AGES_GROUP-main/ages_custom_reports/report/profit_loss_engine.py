# -*- coding: utf-8 -*-

from .financial_report_engine import FinancialReportEngine
from .profit_loss_structure import PROFIT_LOSS_STRUCTURE


class ProfitLossEngine(FinancialReportEngine):
    """Compute hierarchical profit and loss lines (Enterprise-style)."""

    report_structure = PROFIT_LOSS_STRUCTURE
    date_label_fields = ('date_from', 'date_to')

    def _ensure_section_balances(self, *codes):
        for code in codes:
            if code not in self._balances:
                node = next((n for n in self.report_structure if n['code'] == code), None)
                if node and not node.get('expression'):
                    self._build_node(node)

    def _compute_expression(self, expression):
        self._ensure_section_balances('REV', 'COS', 'EXP', 'OIN', 'OEXP')
        rev = self._balances.get('REV', 0.0)
        cos = self._balances.get('COS', 0.0)
        exp = self._balances.get('EXP', 0.0)
        oin = self._balances.get('OIN', 0.0)
        oexp = self._balances.get('OEXP', 0.0)

        if expression == 'gross_profit':
            return rev - cos
        if expression == 'operating_income':
            return rev - cos - exp
        if expression == 'net_profit':
            return rev + oin - cos - exp - oexp
        return 0.0

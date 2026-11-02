# -*- coding: utf-8 -*-

import ast
import operator
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tools.float_utils import float_is_zero

from .tax_return_structure import TAX_RETURN_STRUCTURE, TAX_RETURN_REPORT_NAME


_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class TaxReturnEngine:
    """Enterprise-style Pakistan Tax Return engine (tax_tags + aggregation)."""

    date_label_fields = ('date_from', 'date_to')

    def __init__(self, env, options):
        self.env = env
        self.company = env.company
        self.currency = self.company.currency_id
        self.options = options
        self.date_from = (
            fields.Date.to_date(options['date_from'])
            if options.get('date_from') else None
        )
        self.date_to = fields.Date.to_date(options['date_to'])
        self.comparison = bool(options.get('comparison'))
        self._tag_cache = None

    def get_report_data(self):
        current_amounts = self._compute_period_amounts(self.date_from, self.date_to)
        comparison_amounts = {}
        comparison_from = comparison_to = None
        if self.comparison:
            comparison_from, comparison_to = self._comparison_dates()
            if comparison_from and comparison_to:
                comparison_amounts = self._compute_period_amounts(
                    comparison_from, comparison_to,
                )

        lines = [
            self._build_line(node, current_amounts, comparison_amounts, level=0)
            for node in TAX_RETURN_STRUCTURE
        ]
        return {
            'lines': lines,
            'currency_id': self.currency.id,
            'currency_symbol': self._currency_display(),
            'currency_position': self.currency.position,
            'date_label': self._get_date_label(),
            'period_label': self._get_period_label(),
            'comparison_label': (
                self._get_period_label(comparison_from, comparison_to)
                if self.comparison and comparison_from else ''
            ),
            'comparison': self.comparison,
            'report_name': TAX_RETURN_REPORT_NAME,
            'warnings': self._get_warnings(),
        }

    def flatten_lines(self, lines=None, unfolded_ids=None):
        unfolded_ids = set(unfolded_ids or [])
        unfold_all = self.options.get('unfold_all', True)
        result = []

        def _walk(node):
            result.append({k: v for k, v in node.items() if k != 'children'})
            children = node.get('children') or []
            if not children:
                return
            show_children = (
                not node.get('foldable')
                or unfold_all
                or node.get('id') in unfolded_ids
            )
            if show_children:
                for child in children:
                    _walk(child)

        for line in lines or []:
            _walk(line)
        return result

    def _currency_display(self):
        symbol = (self.currency.symbol or self.currency.name or '').strip()
        if symbol in ('Rs', 'Rs.', '₨'):
            return 'Rs.'
        return symbol

    def _get_date_label(self, date_from=None, date_to=None):
        date_from = date_from if date_from is not None else self.date_from
        date_to = date_to if date_to is not None else self.date_to
        if date_from:
            return (
                f"{fields.Date.to_string(date_from)} — "
                f"{fields.Date.to_string(date_to)}"
            )
        return fields.Date.to_string(date_to) if date_to else ''

    def _get_period_label(self, date_from=None, date_to=None):
        date_from = date_from if date_from is not None else self.date_from
        date_to = date_to if date_to is not None else self.date_to
        if date_from and date_to and hasattr(self.company, '_get_tax_closing_period_boundaries'):
            start, end = self.company._get_tax_closing_period_boundaries(date_from)
            if start == date_from and end == date_to:
                return self.company._get_tax_closing_move_description(
                    self.company._get_tax_periodicity(), date_from, date_to,
                )
        if date_from and date_to:
            month_end = date_from + relativedelta(months=1, days=-1)
            if date_from.day == 1 and date_to == month_end:
                return date_from.strftime('%b %Y')
        return self._get_date_label(date_from, date_to)

    def _comparison_dates(self):
        if not self.date_from or not self.date_to:
            return None, None
        previous_day = self.date_from - relativedelta(days=1)
        if hasattr(self.company, '_get_tax_closing_period_boundaries'):
            return self.company._get_tax_closing_period_boundaries(previous_day)
        month_end = self.date_from + relativedelta(months=1, days=-1)
        if self.date_from.day == 1 and self.date_to == month_end:
            comparison_from = self.date_from - relativedelta(months=1)
            comparison_to = self.date_from - relativedelta(days=1)
            return comparison_from, comparison_to
        delta = self.date_to - self.date_from
        comparison_to = self.date_from - relativedelta(days=1)
        comparison_from = comparison_to - delta
        return comparison_from, comparison_to

    def _get_warnings(self):
        warnings = []
        _formula_by_tag, tag_ids_by_formula = self._resolve_tags()
        if not any(tag_ids_by_formula.values()):
            warnings.append({
                'code': 'missing_tags',
                'message': (
                    'Pakistan tax report tags were not found. Install the '
                    'Pakistan localization (l10n_pk) and configure taxes so '
                    'this report can pick up base and tax amounts.'
                ),
            })
        if self.options.get('target_move') == 'posted':
            domain = [
                ('company_id', 'child_of', self.company.id),
                ('state', '=', 'draft'),
                ('date', '<=', self.date_to),
            ]
            if self.env['account.move'].search_count(domain, limit=1):
                warnings.append({
                    'code': 'unposted_moves',
                    'message': (
                        'There are unposted Journal Entries prior or included '
                        'in this period.'
                    ),
                    'link_label': 'unposted Journal Entries',
                })
        return warnings

    def _company_ids(self):
        return self.env['res.company'].search([
            ('id', 'child_of', self.company.id),
        ]).ids

    def _get_country(self):
        country = self.env.ref('base.pk', raise_if_not_found=False)
        if country:
            return country
        return (
            self.company.account_fiscal_country_id
            or self.company.country_id
        )

    def _collect_tag_formulas(self, nodes=None):
        formulas = set()

        def _walk(node):
            if node.get('base_tag'):
                formulas.add(node['base_tag'])
            if node.get('tax_tag'):
                formulas.add(node['tax_tag'])
            for child in node.get('children') or []:
                _walk(child)

        for node in nodes or TAX_RETURN_STRUCTURE:
            _walk(node)
        return formulas

    def _resolve_tags(self, formulas=None):
        all_formulas = self._collect_tag_formulas()
        if self._tag_cache is None:
            Tag = self.env['account.account.tag'].with_context(
                active_test=False, lang='en_US',
            )
            country = self._get_country()
            country_id = country.id if country else False
            formula_by_tag = {}
            tag_ids_by_formula = {formula: [] for formula in all_formulas}

            for formula in all_formulas:
                tags = Tag._get_tax_tags(formula, country_id)
                if not tags:
                    escaped = (
                        formula.replace('\\', '\\\\')
                        .replace('%', r'\%')
                        .replace('_', r'\_')
                    )
                    tags = Tag.search([
                        ('name', '=like', '_' + escaped),
                        ('applicability', '=', 'taxes'),
                    ])
                for tag in tags:
                    formula_by_tag[tag.id] = (
                        formula,
                        -1.0 if tag.tax_negate else 1.0,
                    )
                    tag_ids_by_formula[formula].append(tag.id)
            self._tag_cache = (formula_by_tag, tag_ids_by_formula)

        formula_by_tag, tag_ids_by_formula = self._tag_cache
        if formulas is None:
            return formula_by_tag, tag_ids_by_formula
        filtered = {
            formula: tag_ids_by_formula.get(formula, [])
            for formula in formulas
        }
        return formula_by_tag, filtered

    def _compute_tag_balances(self, date_from, date_to, formulas):
        result = {formula: 0.0 for formula in formulas}
        formula_by_tag, _tag_ids_by_formula = self._resolve_tags(formulas)
        tag_ids = list(formula_by_tag)
        if not tag_ids or not date_to:
            return result

        company_ids = self._company_ids()
        posted_only = self.options.get('target_move', 'posted') == 'posted'
        params = [
            tuple(tag_ids),
            date_to,
            tuple(company_ids),
        ]
        date_from_sql = ''
        if date_from:
            date_from_sql = 'AND aml.date >= %s'
            params.insert(1, date_from)
        posted_sql = "AND aml.parent_state = 'posted'" if posted_only else ''

        self.env.cr.execute(f"""
            SELECT
                aml_tag.account_account_tag_id,
                SUM(
                    aml.balance
                    * CASE WHEN aml.tax_tag_invert THEN -1 ELSE 1 END
                )
            FROM account_move_line aml
            JOIN account_account_tag_account_move_line_rel aml_tag
                ON aml_tag.account_move_line_id = aml.id
            WHERE aml_tag.account_account_tag_id IN %s
              {date_from_sql}
              AND aml.date <= %s
              AND aml.company_id IN %s
              AND COALESCE(aml.display_type, 'product') NOT IN
                  ('line_section', 'line_note')
              {posted_sql}
            GROUP BY aml_tag.account_account_tag_id
        """, params)

        for tag_id, balance in self.env.cr.fetchall():
            formula, sign = formula_by_tag.get(tag_id, (None, 1.0))
            if formula:
                result[formula] += (balance or 0.0) * sign
        return result

    def _empty_amounts(self):
        return {'base': 0.0, 'tax': 0.0}

    def _compute_period_amounts(self, date_from, date_to):
        formulas = self._collect_tag_formulas()
        tag_balances = self._compute_tag_balances(date_from, date_to, formulas)
        amounts = {}

        def _seed(node):
            values = self._empty_amounts()
            if node.get('base_tag'):
                values['base'] = tag_balances.get(node['base_tag'], 0.0)
            if node.get('tax_tag'):
                values['tax'] = tag_balances.get(node['tax_tag'], 0.0)
            amounts[node['code']] = values
            for child in node.get('children') or []:
                _seed(child)

        for node in TAX_RETURN_STRUCTURE:
            _seed(node)

        pending = True
        guard = 0
        while pending and guard < 8:
            pending = False
            guard += 1

            def _eval_node(node):
                nonlocal pending
                for child in node.get('children') or []:
                    _eval_node(child)
                formula = node.get('tax_formula')
                if not formula:
                    return
                try:
                    amounts[node['code']]['tax'] = self._eval_formula(formula, amounts)
                except KeyError:
                    pending = True

            for node in TAX_RETURN_STRUCTURE:
                _eval_node(node)

        rounding = self.currency.rounding
        for values in amounts.values():
            values['base'] = self.currency.round(values['base'])
            values['tax'] = self.currency.round(values['tax'])
            if float_is_zero(values['base'], precision_rounding=rounding):
                values['base'] = 0.0
            if float_is_zero(values['tax'], precision_rounding=rounding):
                values['tax'] = 0.0
        return amounts

    def _eval_formula(self, formula, amounts):
        expr = formula
        for code, values in sorted(amounts.items(), key=lambda item: len(item[0]), reverse=True):
            expr = expr.replace(f'{code}.tax', repr(values.get('tax', 0.0)))
            expr = expr.replace(f'{code}.base', repr(values.get('base', 0.0)))
        return self._safe_eval(expr)

    def _safe_eval(self, expression):
        tree = ast.parse(expression, mode='eval')

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_BINOPS:
                return _SAFE_BINOPS[type(node.op)](_eval(node.operand))
            if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
                left = _eval(node.left)
                right = _eval(node.right)
                if isinstance(node.op, ast.Div) and not right:
                    return 0.0
                return _SAFE_BINOPS[type(node.op)](left, right)
            raise ValueError(f'Unsupported tax formula: {expression}')

        return float(_eval(tree))

    def _pct(self, current, previous):
        rounding = self.currency.rounding
        if previous is None or float_is_zero(previous, precision_rounding=rounding):
            return False
        return ((current - previous) / abs(previous)) * 100.0

    def _build_line(self, node, current_amounts, comparison_amounts, level):
        code = node['code']
        current = current_amounts.get(code) or self._empty_amounts()
        comparison = comparison_amounts.get(code) or self._empty_amounts()
        children = [
            self._build_line(child, current_amounts, comparison_amounts, level + 1)
            for child in node.get('children') or []
        ]
        tag_ids = []
        if node.get('base_tag') or node.get('tax_tag'):
            _formula_by_tag, tag_ids_by_formula = self._resolve_tags()
            for formula in (node.get('base_tag'), node.get('tax_tag')):
                if formula:
                    tag_ids.extend(tag_ids_by_formula.get(formula) or [])

        return {
            'id': node['id'],
            'code': code,
            'name': node['name'],
            'level': level,
            'line_type': node.get('line_type') or 'tax',
            'foldable': bool(node.get('foldable') and children),
            'show_base': bool(node.get('show_base')),
            'show_tax': bool(node.get('show_tax')),
            'base': current['base'],
            'tax': current['tax'],
            'comp_base': comparison['base'] if self.comparison else False,
            'comp_tax': comparison['tax'] if self.comparison else False,
            'pct_base': (
                self._pct(current['base'], comparison['base'])
                if self.comparison and node.get('show_base') else False
            ),
            'pct_tax': (
                self._pct(current['tax'], comparison['tax'])
                if self.comparison and node.get('show_tax') else False
            ),
            'tag_ids': tag_ids,
            'children': children,
        }

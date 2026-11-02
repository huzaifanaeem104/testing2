# -*- coding: utf-8 -*-
"""Scope, ACL, date, currency and payload helpers for AGES Enterprise Dashboard."""

from datetime import datetime, time, timedelta
import logging

import pytz

from odoo import fields, models
from odoo.osv import expression
from odoo.tools.misc import formatLang, format_date

_logger = logging.getLogger(__name__)

PERIOD_PRESETS = (
    ('today', 'Today'),
    ('yesterday', 'Yesterday'),
    ('week', 'This week'),
    ('month', 'This month'),
    ('last_month', 'Last month'),
    ('quarter', 'This quarter'),
    ('ytd', 'Year to date'),
    ('previous_year', 'Previous year'),
    ('custom', 'Custom range'),
)

COMPANY_FIELD_MAP = {
    'ages.sub.company': ('company_id', 'id'),
    'project.project': ('company_id', 'ages_sub_company_id'),
    'project.task': ('company_id', 'project_id.ages_sub_company_id'),
    'ages.contract': ('company_id', 'sub_company_id'),
    'ages.running.bill': ('company_id', 'sub_company_id'),
    'ages.mobilization.advance': ('company_id', 'sub_company_id'),
    'ages.retention.recovery': ('company_id', 'sub_company_id'),
    'account.move': ('company_id', 'ages_sub_company_id'),
    'account.move.line': ('company_id', 'move_id.ages_sub_company_id'),
    'account.payment': ('company_id', 'ages_sub_company_id'),
    'account.analytic.line': ('company_id', False),
    'ages.expense': ('company_id', 'sub_company_id'),
    'ages.material.consumption': ('company_id', 'sub_company_id'),
    'ages.gate.pass': ('company_id', 'sub_company_id'),
    'purchase.order': ('company_id', False),
    'purchase.order.line': ('company_id', False),
    'purchase.request': ('company_id', False),
    'purchase.request.line': ('company_id', False),
    'stock.picking': ('company_id', False),
    'stock.move': ('company_id', False),
    'stock.quant': ('company_id', False),
    'stock.valuation.layer': ('company_id', False),
    'stock.warehouse.orderpoint': ('company_id', False),
    'sale.order': ('company_id', False),
    'sale.order.line': ('company_id', False),
    'hr.employee': ('company_id', False),
    'hr.attendance': ('employee_id.company_id', False),
    'hr.work.entry': ('company_id', False),
    'hr.payslip': ('company_id', False),
    'hr.contract': ('company_id', False),
    'hr.leave': ('employee_id.company_id', False),
    'account.asset': ('company_id', False),
    'account.asset.line': ('company_id', False),
    'account.asset.asset': ('company_id', False),
    'account.asset.depreciation.line': ('asset_id.company_id', False),
    'asset.transfer': ('company_id', False),
    'quality.check': ('company_id', False),
    'crm.lead': ('company_id', False),
    'mrp.production': ('company_id', False),
    'project.portal.attendance': ('project_id.company_id', False),
    'tier.review': (False, False),
    'crossovered.budget': ('company_id', False),
    'crossovered.budget.lines': ('company_id', False),
    'crossovered.budget.line': ('company_id', False),
    'hr.payslip.line': ('slip_id.company_id', False),
    'hr.payslip.run': ('company_id', False),
    'hr.loan.installment': ('employee_id.company_id', False),
    'construction.boq': ('company_id', False),
    'construction.change.order': ('company_id', False),
    'construction.material.request': ('company_id', False),
    'construction.daily.log': ('company_id', False),
    'construction.progress.entry': ('company_id', False),
    'construction.rfi': ('company_id', False),
    'construction.subcontract': ('company_id', False),
    'construction.equipment.assignment': ('company_id', False),
    'hr.employee.wage.history': ('employee_id.company_id', False),
    'hr.employee.project.tracking': ('employee_id.company_id', False),
    'ages.expense.line': ('expense_id.company_id', False),
    'res.partner': (False, False),
    'ages.deletion.audit': (False, False),
}

PROJECT_FIELD_CANDIDATES = {
    'project.project': ('id',),
    'project.task': ('project_id',),
    'ages.contract': ('project_id',),
    'ages.running.bill': ('project_id',),
    'ages.mobilization.advance': ('project_id',),
    'ages.retention.recovery': ('project_id',),
    'account.move': ('ages_project_id',),
    'account.move.line': ('move_id.ages_project_id',),
    'account.payment': ('ages_project_id',),
    'ages.expense': ('project_id',),
    'ages.material.consumption': ('project_id',),
    'ages.gate.pass': ('project_id',),
    'purchase.order': ('ages_project_id', 'project_id'),
    'purchase.order.line': ('order_id.ages_project_id', 'order_id.project_id'),
    'purchase.request': ('ages_project_id',),
    'purchase.request.line': ('request_id.ages_project_id',),
    'stock.picking': ('project_id', 'construction_project_id'),
    'hr.employee': ('project_id',),
    'hr.contract': ('employee_id.project_id',),
    'hr.employee.wage.history': ('employee_id.project_id',),
    'hr.employee.project.tracking': ('project_id', 'employee_id.project_id'),
    'hr.attendance': ('employee_id.project_id',),
    'hr.payslip': ('project_id', 'employee_id.project_id'),
    'hr.payslip.line': ('slip_id.project_id', 'employee_id.project_id'),
    'hr.work.entry': ('employee_id.project_id',),
    'project.portal.attendance': ('project_id',),
    'sale.order': ('project_id',),
    'account.asset': ('current_project_id',),
    'asset.transfer': ('project_id',),
    'mrp.production': ('construction_project_id',),
    'purchase.request.line': ('request_id.ages_project_id',),
    'ages.expense.line': ('project_id',),
}

CONTRACT_FIELD_MAP = {
    'ages.contract': 'id',
    'ages.running.bill': 'contract_id',
    'ages.mobilization.advance': 'contract_id',
    'ages.retention.recovery': 'contract_id',
    'account.move': 'ages_contract_id',
    'account.move.line': 'move_id.ages_contract_id',
    'account.payment': 'ages_contract_id',
}

PARTNER_FIELD_MAP = {
    'ages.contract': 'partner_id',
    'ages.running.bill': 'partner_id',
    'ages.mobilization.advance': 'partner_id',
    'ages.retention.recovery': 'partner_id',
    'account.move': 'partner_id',
    'account.move.line': 'partner_id',
    'account.payment': 'partner_id',
    'ages.expense': 'vendor_id',
    'purchase.order': 'partner_id',
    'purchase.order.line': 'order_id.partner_id',
    'purchase.request': ('supplier_id', 'requested_by'),
    'purchase.request.line': 'supplier_id',
    'sale.order': 'partner_id',
    'sale.order.line': 'order_id.partner_id',
    'ages.gate.pass': 'partner_id',
    'res.partner': 'id',
}

AML_POSTED_DOMAIN = [
    ('parent_state', '=', 'posted'),
    ('display_type', 'not in', ('line_section', 'line_note')),
]


class AgesEnterpriseDashboard(models.AbstractModel):
    _name = 'ages.enterprise.dashboard'
    _description = 'AGES Enterprise Management Dashboard'

    def _can_read(self, model_name):
        if not model_name or model_name not in self.env:
            return False
        try:
            return bool(self.env['ir.model.access'].check(model_name, 'read', raise_exception=False))
        except Exception:
            return False

    def _user_in_group(self, xmlid):
        try:
            return bool(self.env.user.has_group(xmlid))
        except Exception:
            return False

    def _user_in_any_group(self, *xmlids):
        return any(self._user_in_group(xmlid) for xmlid in xmlids)

    def _has_field(self, model_name, field_name):
        return self._can_read(model_name) and field_name in self.env[model_name]._fields

    def _field_is_stored(self, model_name, field_name):
        if not self._has_field(model_name, field_name):
            return False
        return bool(self.env[model_name]._fields[field_name].store)

    def _field_path_exists(self, model_name, path):
        if not path or not self._can_read(model_name):
            return False
        Model = self.env[model_name]
        names = path.split('.')
        for index, name in enumerate(names):
            if name not in Model._fields:
                return False
            field = Model._fields[name]
            if index < len(names) - 1:
                if not field.comodel_name or field.comodel_name not in self.env:
                    return False
                Model = self.env[field.comodel_name]
        return True

    def _id_list(self, value, allow_zero=False):
        if value in (None, False, ''):
            return []
        values = value if isinstance(value, (list, tuple, set)) else [value]
        result = []
        for item in values:
            try:
                item = int(item)
            except (TypeError, ValueError):
                continue
            if item > 0 or (allow_zero and item == 0):
                if item not in result:
                    result.append(item)
        return result

    def _config_int(self, key, default):
        try:
            value = self.env['ir.config_parameter'].sudo().get_param(key)
            return int(value) if value not in (None, False, '') else default
        except Exception:
            return default

    def _company(self, scope):
        company_ids = [cid for cid in (scope.get('company_ids') or []) if cid]
        Company = self.env['res.company'].with_context(button_access_skip=True)
        if company_ids:
            return Company.browse(company_ids[0])
        return self.env.company.with_context(button_access_skip=True)

    def _currency(self, scope):
        Currency = self.env['res.currency'].with_context(button_access_skip=True)
        reporting_currency_id = scope.get('reporting_currency_id')
        if reporting_currency_id and 'res.currency' in self.env:
            currency = Currency.browse(reporting_currency_id).exists()
            if currency:
                return currency
        return self._company(scope).currency_id

    def _format_money(self, amount, scope):
        currency = self._currency(scope)
        return formatLang(self.env, amount or 0.0, currency_obj=currency)

    def _format_date(self, value):
        if not value:
            return ''
        return format_date(self.env, value)

    def _convert_amount(self, amount, from_currency, scope, on_date=None, company=None):
        amount = amount or 0.0
        company = company or self._company(scope)
        target = self._currency(scope)
        if not from_currency or from_currency == target:
            return amount
        return from_currency._convert(
            amount, target, company, on_date or scope.get('date_to') or fields.Date.context_today(self)
        )

    def _first_existing_path(self, model_name, candidates):
        if isinstance(candidates, str):
            candidates = (candidates,)
        for path in candidates:
            if self._field_path_exists(model_name, path):
                return path
        return False

    def _project_path(self, model_name):
        return self._first_existing_path(model_name, PROJECT_FIELD_CANDIDATES.get(model_name, ()))

    def _company_domain(self, model_name, scope):
        domain = []
        mapping = COMPANY_FIELD_MAP.get(model_name, ('company_id', False))
        legal_path, sub_path = mapping
        company_ids = [cid for cid in (scope.get('company_ids') or []) if cid]
        if legal_path and company_ids and self._field_path_exists(model_name, legal_path):
            domain.append((legal_path, 'in', company_ids))
        elif legal_path and scope.get('company_ids') == [0]:
            domain.append((legal_path, 'in', [0]))
        sub_ids = [sid for sid in (scope.get('sub_company_ids') or []) if sid]
        include_unassigned = bool(scope.get('include_unassigned'))
        if sub_path and self._field_path_exists(model_name, sub_path) and (sub_ids or include_unassigned):
            if include_unassigned and sub_ids:
                domain.append('|')
                domain.append((sub_path, 'in', sub_ids))
                domain.append((sub_path, '=', False))
            elif include_unassigned:
                domain.append((sub_path, '=', False))
            elif sub_ids:
                domain.append((sub_path, 'in', sub_ids))
        return domain

    def _scope_domain(self, model_name, scope, extra=None):
        domain = self._company_domain(model_name, scope)
        project_ids = scope.get('project_ids')
        if not project_ids:
            project_ids = None
        project_path = self._project_path(model_name)
        if (
            model_name == 'account.move.line'
            and project_ids
            and self._has_field('project.project', 'account_id')
            and self._has_field('account.move.line', 'analytic_distribution')
        ):
            analytic_ids = self.env['project.project'].search([
                ('id', 'in', project_ids),
                ('account_id', '!=', False),
            ]).mapped('account_id').ids
            domain.append(('analytic_distribution', 'in', analytic_ids or [0]))
        elif project_ids and project_path:
            domain.append((project_path, 'in', project_ids))
        contract_ids = scope.get('contract_ids') or []
        contract_path = CONTRACT_FIELD_MAP.get(model_name)
        if contract_ids and contract_path and self._field_path_exists(model_name, contract_path):
            domain.append((contract_path, 'in', contract_ids))
        partner_ids = scope.get('partner_ids') or []
        partner_path = PARTNER_FIELD_MAP.get(model_name)
        if isinstance(partner_path, tuple):
            partner_path = self._first_existing_path(model_name, partner_path)
        if partner_ids and partner_path and self._field_path_exists(model_name, partner_path):
            domain.append((partner_path, 'in', partner_ids))
        vendor_ids = scope.get('vendor_ids') or []
        if vendor_ids and model_name in (
            'purchase.order', 'purchase.order.line', 'purchase.request',
            'purchase.request.line', 'ages.expense', 'account.move',
        ):
            vendor_path = {
                'purchase.order': 'partner_id',
                'purchase.order.line': 'order_id.partner_id',
                'purchase.request': 'supplier_id',
                'purchase.request.line': 'supplier_id',
                'ages.expense': 'vendor_id',
                'account.move': 'partner_id',
            }[model_name]
            if model_name == 'account.move':
                domain.extend([('move_type', 'in', ('in_invoice', 'in_refund')), ('partner_id', 'in', vendor_ids)])
            elif self._field_path_exists(model_name, vendor_path):
                domain.append((vendor_path, 'in', vendor_ids))
        department_ids = scope.get('department_ids') or []
        dept_path = {
            'hr.employee': 'department_id',
            'hr.payslip': 'department_id',
            'hr.payslip.line': 'employee_id.department_id',
            'hr.attendance': 'employee_id.department_id',
            'hr.department': 'id',
            'hr.leave': 'employee_id.department_id',
            'project.portal.attendance': 'employee_id.department_id',
            'hr.contract': 'employee_id.department_id',
            'hr.employee.wage.history': 'employee_id.department_id',
            'hr.employee.project.tracking': 'employee_id.department_id',
        }.get(model_name)
        if department_ids and dept_path and self._field_path_exists(model_name, dept_path):
            domain.append((dept_path, 'in', department_ids))
        employee_ids = scope.get('employee_ids') or []
        emp_path = {
            'hr.employee': 'id',
            'hr.attendance': 'employee_id',
            'hr.payslip': 'employee_id',
            'hr.payslip.line': 'employee_id',
            'hr.leave': 'employee_id',
            'hr.work.entry': 'employee_id',
            'project.portal.attendance': 'employee_id',
            'hr.contract': 'employee_id',
            'hr.employee.wage.history': 'employee_id',
            'hr.employee.project.tracking': 'employee_id',
            'hr.loan.installment': 'employee_id',
        }.get(model_name)
        if employee_ids and emp_path and self._field_path_exists(model_name, emp_path):
            domain.append((emp_path, 'in', employee_ids))
        product_ids = scope.get('product_ids') or []
        product_path = {
            'purchase.order.line': 'product_id',
            'purchase.request.line': 'product_id',
            'stock.quant': 'product_id',
            'stock.move': 'product_id',
            'stock.move.line': 'product_id',
            'stock.warehouse.orderpoint': 'product_id',
            'sale.order.line': 'product_id',
            'quality.check': 'product_id',
            'mrp.production': 'product_id',
        }.get(model_name)
        if product_ids and product_path and self._field_path_exists(model_name, product_path):
            domain.append((product_path, 'in', product_ids))
        product_category_ids = scope.get('product_category_ids') or []
        if product_category_ids and product_path and self._field_path_exists(model_name, '%s.categ_id' % product_path):
            domain.append(('%s.categ_id' % product_path, 'in', product_category_ids))
        warehouse_ids = scope.get('warehouse_ids') or []
        wh_path = {
            'stock.warehouse': 'id',
            'stock.picking': 'picking_type_id.warehouse_id',
            'stock.quant': 'location_id.warehouse_id',
            'stock.move': 'picking_id.picking_type_id.warehouse_id',
            'stock.move.line': 'picking_id.picking_type_id.warehouse_id',
            'stock.warehouse.orderpoint': 'warehouse_id',
        }.get(model_name)
        if warehouse_ids and wh_path and self._field_path_exists(model_name, wh_path):
            domain.append((wh_path, 'in', warehouse_ids))
        location_ids = scope.get('location_ids') or []
        location_path = {
            'stock.quant': 'location_id',
            'stock.move': 'location_id',
            'stock.move.line': 'location_id',
            'stock.warehouse.orderpoint': 'location_id',
            'ages.gate.pass': 'location_id',
            'account.asset': 'current_location_id',
            'asset.transfer': 'location_from_id',
        }.get(model_name)
        if location_ids and location_path and self._field_path_exists(model_name, location_path):
            domain.append((location_path, 'in', location_ids))
        journal_ids = scope.get('journal_ids') or []
        journal_path = {
            'account.move': 'journal_id',
            'account.move.line': 'journal_id',
            'account.payment': 'journal_id',
            'ages.expense': 'journal_id',
        }.get(model_name)
        if journal_ids and journal_path and self._field_path_exists(model_name, journal_path):
            domain.append((journal_path, 'in', journal_ids))
        account_ids = scope.get('account_ids') or []
        account_path = {
            'account.move.line': 'account_id',
            'ages.expense.line': 'account_id',
        }.get(model_name)
        if account_ids and account_path and self._field_path_exists(model_name, account_path):
            domain.append((account_path, 'in', account_ids))
        analytic_ids = scope.get('analytic_account_ids') or []
        analytic_path = {
            'project.project': 'account_id',
            'purchase.order': 'ages_analytic_account_id',
            'purchase.request': 'ages_analytic_account_id',
            'ages.expense': 'analytic_account_id',
            'ages.expense.line': 'analytic_account_id',
            'hr.payslip': 'analytic_account_id',
            'hr.payslip.line': 'slip_id.analytic_account_id',
            'asset.transfer': 'analytic_account_id',
            'account.asset.asset': 'account_analytic_id',
        }.get(model_name)
        if analytic_ids and analytic_path and self._field_path_exists(model_name, analytic_path):
            domain.append((analytic_path, 'in', analytic_ids))
        salesperson_ids = scope.get('salesperson_ids') or []
        salesperson_path = {'sale.order': 'user_id', 'crm.lead': 'user_id'}.get(model_name)
        if salesperson_ids and salesperson_path and self._field_path_exists(model_name, salesperson_path):
            domain.append((salesperson_path, 'in', salesperson_ids))
        sales_team_ids = scope.get('sales_team_ids') or []
        team_path = {'sale.order': 'team_id', 'crm.lead': 'team_id'}.get(model_name)
        if sales_team_ids and team_path and self._field_path_exists(model_name, team_path):
            domain.append((team_path, 'in', sales_team_ids))
        requester_ids = scope.get('requester_ids') or []
        requester_path = {
            'purchase.request': 'requested_by',
            'purchase.request.line': 'requested_by',
        }.get(model_name)
        if requester_ids and requester_path and self._field_path_exists(model_name, requester_path):
            domain.append((requester_path, 'in', requester_ids))
        approval_statuses = scope.get('approval_statuses') or []
        approval_path = {
            'purchase.request': 'validation_status',
            'account.payment': 'validation_status',
            'tier.review': 'status',
        }.get(model_name)
        if approval_statuses and approval_path and self._field_path_exists(model_name, approval_path):
            domain.append((approval_path, 'in', approval_statuses))
        document_statuses = scope.get('document_statuses') or []
        if document_statuses and self._has_field(model_name, 'state'):
            valid_states = set(dict(self.env[model_name]._fields['state']._description_selection(self.env)))
            statuses = [state for state in document_statuses if state in valid_states]
            domain.append(('state', 'in', statuses or ['__invalid__']))
        labour_categories = scope.get('labour_categories') or []
        labour_path = {
            'hr.employee': 'ages_employee_category',
            'hr.attendance': 'employee_id.ages_employee_category',
            'hr.payslip': 'employee_id.ages_employee_category',
            'project.portal.attendance': 'employee_id.ages_employee_category',
        }.get(model_name)
        if labour_categories and labour_path and self._field_path_exists(model_name, labour_path):
            domain.append((labour_path, 'in', labour_categories))
        currency_ids = scope.get('currency_ids') or []
        if currency_ids and self._has_field(model_name, 'currency_id'):
            domain.append(('currency_id', 'in', currency_ids))
        if extra:
            domain = expression.AND([domain, extra])
        return domain

    def _first_date_field(self, model_name, candidates):
        for name in candidates:
            if self._has_field(model_name, name):
                return name
        return False

    def _distinct_count(self, model_name, domain, groupby):
        if not self._can_read(model_name) or not self._field_path_exists(model_name, groupby):
            return 0
        try:
            rows = self.env[model_name].read_group(domain, ['id:count'], [groupby], lazy=False)
        except Exception as exc:
            _logger.warning('Dashboard distinct count failed on %s.%s: %s', model_name, groupby, exc)
            return 0
        return len(rows)

    def _run_rate_projection(self, period_value, date_from, date_to):
        if period_value in (None, False) or not date_from or not date_to:
            return False
        today = fields.Date.context_today(self)
        elapsed_end = min(date_to, today)
        elapsed_days = (elapsed_end - date_from).days + 1
        total_days = (date_to - date_from).days + 1
        if elapsed_days <= 0 or total_days <= 0:
            return False
        if elapsed_days >= total_days:
            return period_value
        return (period_value / float(elapsed_days)) * total_days

    def _date_domain(self, field_name, date_from, date_to):
        domain = []
        if date_from:
            domain.append((field_name, '>=', date_from))
        if date_to:
            domain.append((field_name, '<=', date_to))
        return domain

    def _datetime_date_domain(self, field_name, date_from, date_to):
        """Convert local date boundaries to UTC for datetime domains."""
        timezone_name = self.env.user.tz or self.env.company.partner_id.tz or 'UTC'
        try:
            timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            timezone = pytz.UTC
        domain = []
        if date_from:
            local_start = timezone.localize(datetime.combine(date_from, time.min))
            utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            domain.append((field_name, '>=', fields.Datetime.to_string(utc_start)))
        if date_to:
            local_end = timezone.localize(datetime.combine(date_to, time.max))
            utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
            domain.append((field_name, '<=', fields.Datetime.to_string(utc_end)))
        return domain

    def _read_group_sum(self, model_name, domain, field_name, groupby=None):
        if not self._can_read(model_name):
            return [] if groupby else 0.0
        Model = self.env[model_name]
        if field_name not in Model._fields:
            return [] if groupby else 0.0
        try:
            rows = Model.read_group(domain, ['%s:sum' % field_name], groupby or [], lazy=False)
        except Exception as exc:
            _logger.warning('Dashboard read_group failed on %s.%s: %s', model_name, field_name, exc)
            return [] if groupby else 0.0
        if groupby:
            return rows
        return rows[0].get(field_name) or 0.0 if rows else 0.0

    def _currency_sum(
        self, model_name, domain, field_name, scope,
        currency_field='currency_id', company_field='company_id', date_field=False,
        company_currency=False,
    ):
        """Sum monetary records in the selected reporting currency.

        ``company_currency`` is used for signed accounting fields whose stored
        value is already in each record company's currency.
        """
        if not self._can_read(model_name) or not self._has_field(model_name, field_name):
            return 0.0
        target = self._currency(scope)
        fields_to_fetch = [field_name]
        if self._field_path_exists(model_name, company_field):
            fields_to_fetch.append(company_field)
        if not company_currency and self._field_path_exists(model_name, currency_field):
            fields_to_fetch.append(currency_field)
        if date_field and self._field_path_exists(model_name, date_field):
            fields_to_fetch.append(date_field)
        scope_companies = self.env['res.company'].browse(
            [cid for cid in (scope.get('company_ids') or []) if cid]
        ).exists() or self.env.companies
        if all(company.currency_id == target for company in scope_companies):
            return self._read_group_sum(model_name, domain, field_name) or 0.0
        records = self.env[model_name].search_fetch(domain, list(dict.fromkeys(fields_to_fetch)))
        total = 0.0
        for record in records:
            company = record[company_field] if company_field in record._fields else self._company(scope)
            source_currency = company.currency_id if company_currency else (
                record[currency_field] if currency_field in record._fields else company.currency_id
            )
            conversion_date = record[date_field] if date_field and date_field in record._fields else scope.get('date_to')
            total += self._convert_amount(
                record[field_name], source_currency, scope,
                on_date=conversion_date, company=company,
            )
        return total

    def _live_ar_ap(self, scope):
        rec_domain = self._scope_domain('account.move', scope, [
            ('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
        ])
        pay_domain = self._scope_domain('account.move', scope, [
            ('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted'),
        ])
        receivables = self._read_group_sum(
            'account.move', rec_domain, 'amount_residual_signed'
        ) if self._can_read('account.move') else 0.0
        payables = abs(self._read_group_sum(
            'account.move', pay_domain, 'amount_residual_signed'
        ) or 0.0) if self._can_read('account.move') else 0.0
        return receivables or 0.0, payables, rec_domain, pay_domain

    def _snapshot_ar_ap(self, scope):
        """Prefer AgedPartnerBalanceEngine totals as-of date_to; else live residual."""
        live_ar, live_ap, rec_domain, pay_domain = self._live_ar_ap(scope)
        aged_ar = self._aged_partner_totals(scope, 'receivable')
        aged_ap = self._aged_partner_totals(scope, 'payable')
        prev_ar = prev_ap = False
        if scope.get('compare_period') not in (None, False, 'none') and scope.get('previous_to'):
            prev_scope = dict(scope, date_to=scope['previous_to'])
            if aged_ar:
                prev_aged_ar = self._aged_partner_totals(prev_scope, 'receivable')
                prev_ar = prev_aged_ar['total'] if prev_aged_ar else False
            if aged_ap:
                prev_aged_ap = self._aged_partner_totals(prev_scope, 'payable')
                prev_ap = prev_aged_ap['total'] if prev_aged_ap else False
        return {
            'receivables': aged_ar['total'] if aged_ar else live_ar,
            'payables': aged_ap['total'] if aged_ap else live_ap,
            'previous_receivables': prev_ar,
            'previous_payables': prev_ap,
            'live_ar': live_ar,
            'live_ap': live_ap,
            'aged_ar': aged_ar,
            'aged_ap': aged_ap,
            'rec_domain': rec_domain,
            'pay_domain': pay_domain,
            'ar_basis': 'aged_engine' if aged_ar else 'live_residual',
            'ap_basis': 'aged_engine' if aged_ap else 'live_residual',
        }

    def _record_path_value(self, record, path):
        value = record
        for name in path.split('.'):
            if not value or name not in value._fields:
                return False
            value = value[name]
        return value

    def _currency_grouped(
        self, model_name, domain, field_name, groupby, scope,
        currency_field='currency_id', company_field='company_id', date_field=False,
        company_currency=False, limit=10, abs_value=True,
    ):
        if (
            not self._can_read(model_name)
            or not self._has_field(model_name, field_name)
            or not self._field_path_exists(model_name, groupby)
        ):
            return []
        root_group_field = groupby.split('.')[0]
        fields_to_fetch = [field_name, root_group_field]
        for field_name_to_add in (currency_field, company_field, date_field):
            if field_name_to_add and self._has_field(model_name, field_name_to_add):
                fields_to_fetch.append(field_name_to_add)
        records = self.env[model_name].search_fetch(domain, list(dict.fromkeys(fields_to_fetch)))
        buckets = {}
        for record in records:
            group = self._record_path_value(record, groupby)
            group_id = group.id if getattr(group, 'id', False) else False
            group_name = group.display_name if group_id else 'Unassigned'
            company = record[company_field] if company_field in record._fields else self._company(scope)
            source_currency = company.currency_id if company_currency else (
                record[currency_field] if currency_field in record._fields else company.currency_id
            )
            conversion_date = record[date_field] if date_field and date_field in record._fields else scope.get('date_to')
            amount = self._convert_amount(
                record[field_name], source_currency, scope,
                on_date=conversion_date, company=company,
            )
            key = group_id or 0
            bucket = buckets.setdefault(key, {'name': group_name, 'amount': 0.0, 'res_id': group_id})
            bucket['amount'] += amount
        rows = []
        for bucket in buckets.values():
            amount = abs(bucket['amount']) if abs_value else bucket['amount']
            rows.append({
                'name': bucket['name'],
                'amount': round(amount, 2),
                'formatted': self._format_money(amount, scope),
                'res_id': bucket['res_id'],
            })
        rows.sort(key=lambda item: abs(item['amount']), reverse=True)
        return rows[:limit] if limit else rows

    def _search_count(self, model_name, domain):
        if not self._can_read(model_name):
            return 0
        try:
            return self.env[model_name].search_count(domain)
        except Exception as exc:
            _logger.warning('Dashboard search_count failed on %s: %s', model_name, exc)
            return 0

    def _search_read(self, model_name, domain, fields, limit=20, order=None):
        if not self._can_read(model_name):
            return []
        try:
            limit = 200 if limit in (0, False, None) else int(limit)
        except (TypeError, ValueError):
            limit = 20
        limit = min(max(limit, 1), 500)
        existing = [name for name in fields if name == 'id' or name in self.env[model_name]._fields]
        try:
            return self.env[model_name].search_read(domain, existing, limit=limit, order=order)
        except Exception as exc:
            _logger.warning('Dashboard search_read failed on %s: %s', model_name, exc)
            return []

    def _aml_posted_domain(self, scope, extra=None):
        domain = list(AML_POSTED_DOMAIN)
        domain = expression.AND([domain, self._scope_domain('account.move.line', scope)])
        if extra:
            domain = expression.AND([domain, extra])
        return domain

    def _aml_sum(self, scope, extra, date_from=None, date_to=None, date_field='date', invert=False):
        if not self._can_read('account.move.line'):
            return 0.0
        has_explicit_analytic_domain = any(
            isinstance(leaf, (list, tuple))
            and len(leaf) == 3
            and leaf[0] == 'analytic_distribution'
            for leaf in (extra or [])
        )
        if scope.get('project_ids') and not has_explicit_analytic_domain:
            return self._analytic_project_total(
                scope, extra, date_from, date_to, invert=invert
            )
        domain = self._aml_posted_domain(scope, extra)
        domain = expression.AND([domain, self._date_domain(date_field, date_from, date_to)])
        target_currency = self._currency(scope)
        company_ids = [cid for cid in scope.get('company_ids', []) if cid]
        companies = self.env['res.company'].browse(company_ids).exists() if company_ids else self.env.companies
        needs_conversion = any(company.currency_id != target_currency for company in companies)
        if needs_conversion:
            amount = 0.0
            lines = self.env['account.move.line'].search_fetch(
                domain, ['balance', 'company_id', 'date']
            )
            for line in lines:
                amount += self._convert_amount(
                    line.balance,
                    line.company_id.currency_id,
                    scope,
                    on_date=line.date,
                    company=line.company_id,
                )
        else:
            amount = self._read_group_sum('account.move.line', domain, 'balance')
        return -(amount or 0.0) if invert else (amount or 0.0)

    def _month_starts(self, scope, months=6):
        date_to = scope.get('date_to') or fields.Date.context_today(self)
        cursor = date_to.replace(day=1)
        buckets = []
        for _index in range(months):
            buckets.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        buckets.reverse()
        return buckets, date_to

    def _monthly_aml_trend(self, scope, extra, invert=False, months=6):
        buckets, date_to = self._month_starts(scope, months)
        labels, values = [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            values.append(round(self._aml_sum(scope, extra, month_start, month_end, invert=invert), 2))
        return labels, values

    def _monthly_model_sum(self, model_name, scope, extra, date_field, amount_field, months=6, abs_value=False):
        if not self._can_read(model_name) or not self._has_field(model_name, amount_field):
            return [], []
        buckets, date_to = self._month_starts(scope, months)
        labels, values = [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            domain = self._scope_domain(model_name, scope, extra or [])
            domain += self._typed_date_domain(model_name, date_field, month_start, month_end)
            amount = self._read_group_sum(model_name, domain, amount_field) or 0.0
            values.append(round(abs(amount) if abs_value else amount, 2))
        return labels, values

    def _monthly_model_count(self, model_name, scope, extra, date_field, months=6):
        if not self._can_read(model_name):
            return [], []
        buckets, date_to = self._month_starts(scope, months)
        labels, values = [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            domain = self._scope_domain(model_name, scope, extra or [])
            domain += self._typed_date_domain(model_name, date_field, month_start, month_end)
            values.append(self._search_count(model_name, domain))
        return labels, values

    def _typed_date_domain(self, model_name, date_field, date_from, date_to):
        if not self._has_field(model_name, date_field):
            return []
        field = self.env[model_name]._fields[date_field]
        if field.type == 'datetime':
            return self._datetime_date_domain(date_field, date_from, date_to)
        return self._date_domain(date_field, date_from, date_to)

    def _unassigned_analytic_amount(self, scope, extra, date_from, date_to, invert=False):
        extra = list(extra or []) + [('analytic_distribution', '=', False)]
        return abs(self._aml_sum(scope, extra, date_from, date_to, invert=invert) or 0.0)

    def _analytic_project_rows(self, scope, extra, date_from, date_to, invert=False, limit=0):
        if (
            not self._can_read('project.project')
            or not self._can_read('account.move.line')
            or not self._has_field('project.project', 'account_id')
        ):
            return []
        project_domain = self._company_domain('project.project', scope) + [('account_id', '!=', False)]
        if scope.get('project_ids'):
            project_domain.append(('id', 'in', scope.get('project_ids')))
        projects = self.env['project.project'].search_fetch(
            project_domain, ['name', 'account_id']
        )
        analytic_to_projects = {}
        for project in projects:
            analytic_to_projects.setdefault(project.account_id.id, []).append(project)
        if not analytic_to_projects:
            return []
        aml_scope = dict(scope, project_ids=None)
        domain = self._aml_posted_domain(
            aml_scope, list(extra or []) + [
                ('analytic_distribution', '!=', False),
                ('analytic_distribution', 'in', list(analytic_to_projects)),
            ],
        )
        domain = expression.AND([domain, self._date_domain('date', date_from, date_to)])
        lines = self.env['account.move.line'].search_fetch(
            domain, ['balance', 'analytic_distribution', 'company_id', 'date']
        )
        amounts = {project.id: 0.0 for project in projects}
        for line in lines:
            converted = self._convert_amount(
                line.balance, line.company_id.currency_id, scope,
                on_date=line.date, company=line.company_id,
            )
            distribution = line.analytic_distribution or {}
            for key, percentage in distribution.items():
                ids = {
                    int(item) for item in str(key).split(',')
                    if item and str(item).isdigit()
                }
                for analytic_id in ids.intersection(analytic_to_projects):
                    contribution = converted * (float(percentage or 0.0) / 100.0)
                    for project in analytic_to_projects[analytic_id]:
                        amounts[project.id] += contribution
        rows = []
        for project in projects:
            amount = amounts.get(project.id, 0.0)
            if invert:
                amount = -amount
            raw_amount = amount
            amount = abs(raw_amount)
            rows.append({
                'name': project.display_name,
                'amount': round(amount, 2),
                'formatted': self._format_money(amount, scope),
                'res_id': project.id,
                'analytic_account_id': project.account_id.id,
                'raw_amount': round(raw_amount, 2),
            })
        rows.sort(key=lambda item: item['amount'], reverse=True)
        return rows[:limit] if limit else rows

    def _analytic_project_total(self, scope, extra, date_from, date_to, invert=False):
        return sum(
            row['raw_amount']
            for row in self._analytic_project_rows(
                scope, extra, date_from, date_to, invert=invert
            )
        )

    def _monthly_analytic_project_trend(self, scope, extra, invert=False, months=6):
        buckets, date_to = self._month_starts(scope, months)
        labels, values = [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            values.append(round(self._analytic_project_total(
                scope, extra, month_start, month_end, invert=invert
            ), 2))
        return labels, values

    def _ra_sums(self, scope, extra=None, date_from=None, date_to=None):
        empty = {
            'work': 0.0, 'rebate': 0.0, 'ex_rebate': 0.0, 'material': 0.0, 'ex_rebate_mr': 0.0,
            'sales_tax': 0.0, 'receivable_ex': 0.0, 'receivable': 0.0, 'mobilization': 0.0,
            'retention': 0.0, 'wth': 0.0, 'net': 0.0,
        }
        if not self._can_read('ages.running.bill'):
            return empty
        domain = self._scope_domain('ages.running.bill', scope, extra or [])
        if date_from or date_to:
            domain += self._date_domain('date', date_from, date_to)
        mapping = {
            'work': 'value_of_work_done',
            'rebate': 'rebate_amount',
            'ex_rebate': 'ex_rebate_value',
            'material': 'material_recovery',
            'ex_rebate_mr': 'ex_rebate_mr_value',
            'sales_tax': 'sales_tax_amount',
            'receivable_ex': 'total_receivable_ex_sales_tax',
            'receivable': 'total_receivable',
            'mobilization': 'mobilization_amount',
            'retention': 'retention_amount',
            'wth': 'wth_amount',
            'net': 'net_amount',
        }
        result = {}
        for key, fname in mapping.items():
            result[key] = self._currency_sum(
                'ages.running.bill', domain, fname, scope,
                date_field='date', company_currency=True,
            ) if self._has_field('ages.running.bill', fname) else 0.0
        return result

    def _kpi(self, scope, key, label, value, previous=None, action_key=False, tooltip='', status=False, suffix=False, basis='flow', date_field='', formula='', kind=False, exclusions='', limitations='', model='', fields_used=''):
        value = 0.0 if value in (None, False) else value
        previous = previous if previous is not None else False
        delta = False
        direction = 'flat'
        comparable = previous not in (None, False)
        if comparable:
            delta = value - (previous or 0.0)
            if abs(previous or 0.0) > 0.0001:
                pct = delta / abs(previous) * 100.0
            else:
                pct = False
                direction = 'flat'
                comparable = False
            if comparable and delta > 0:
                direction = 'up'
            elif comparable and delta < 0:
                direction = 'down'
        else:
            pct = False
        format_kind = kind or ('count' if suffix is not False else 'money')
        formatted = self._format_kpi_value(value, scope, format_kind, suffix)
        why = tooltip or formula or ('%s (%s)' % (label, basis))
        if (not model or not date_field) and action_key:
            spec = self._action_specs().get(action_key) or {}
            model = model or spec.get('model') or ''
            date_field = date_field or spec.get('date_field') or spec.get('through_date_field') or ''
        target = self._kpi_target(scope, key)
        variance = False
        variance_pct = False
        target_status = 'target_not_configured'
        if target not in (None, False):
            variance = value - target
            if abs(target) > 0.0001:
                variance_pct = variance / abs(target) * 100.0
            warn_pct = self._config_int('ages_enterprise_dashboard.target_warn_pct', 10)
            crit_pct = self._config_int('ages_enterprise_dashboard.target_critical_pct', 20)
            gap = abs(variance_pct or 0.0)
            if gap >= crit_pct:
                target_status = 'critical_variance'
            elif gap >= warn_pct:
                target_status = 'below_target' if variance < 0 else 'above_target'
            else:
                target_status = 'on_target'
        return {
            'key': key,
            'label': label,
            'value': value,
            'formatted': formatted,
            'kind': format_kind,
            'previous': previous if comparable else False,
            'previous_formatted': (
                self._format_kpi_value(previous, scope, format_kind, suffix)
                if comparable else False
            ),
            'delta': delta if comparable else False,
            'percent': pct if comparable else False,
            'direction': direction if comparable else 'flat',
            'comparison_label': self._comparison_label(scope) if comparable else 'No prior comparable period',
            'status': status or direction,
            'action_key': action_key,
            'tooltip': why,
            'basis': basis,
            'classification': basis,
            'date_field': date_field,
            'formula': formula or why,
            'exclusions': exclusions,
            'limitations': limitations,
            'model': model,
            'fields_used': fields_used,
            'target': target,
            'target_formatted': self._format_kpi_value(target, scope, format_kind, suffix) if target not in (None, False) else 'Target not configured',
            'variance': variance,
            'variance_pct': variance_pct,
            'target_status': target_status,
            'unavailable': False,
        }

    def _format_kpi_value(self, value, scope, kind, suffix=False):
        if value in (None, False):
            return ''
        if kind in ('money', 'currency'):
            return self._format_money(value, scope)
        if kind == 'percent':
            return '%s%%' % formatLang(self.env, value or 0.0)
        extra = '' if suffix in (False, None) else str(suffix)
        return '%s%s' % (formatLang(self.env, value or 0.0), extra)

    def _comparison_label(self, scope):
        period = scope.get('period') or 'month'
        compare = scope.get('compare_period') or 'previous_period'
        if compare == 'previous_year':
            return 'vs previous year'
        if compare == 'none':
            return 'No comparison'
        labels = {
            'today': 'vs yesterday',
            'week': 'vs previous week',
            'month': 'vs previous month',
            'quarter': 'vs previous quarter',
            'year': 'vs previous year-to-date',
            'ytd': 'vs previous year-to-date',
        }
        return labels.get(period, 'vs previous period')

    def _kpi_target(self, scope, key):
        if not key:
            return False
        param = self.env['ir.config_parameter'].sudo().get_param(
            'ages_enterprise_dashboard.target.%s' % key
        )
        if param not in (None, False, ''):
            try:
                return float(param)
            except (TypeError, ValueError):
                pass
        if 'ages.dashboard.kpi.target' in self.env and self._can_read('ages.dashboard.kpi.target'):
            company = self._company(scope)
            target = self.env['ages.dashboard.kpi.target'].search([
                ('kpi_key', '=', key),
                ('company_id', 'in', [company.id, False]),
            ], limit=1, order='company_id desc')
            if target:
                return target.target_value
        return False

    def _kpi_registry_summary(self):
        return [
            {'key': 'revenue', 'dashboard': 'finance', 'label': 'Revenue', 'model': 'account.move.line', 'fields': 'balance, account_id.account_type, parent_state, date', 'basis': 'flow', 'date_field': 'date', 'formula': 'SUM(balance) posted income AML, sign-inverted', 'group': 'account.group_account_readonly'},
            {'key': 'expenses', 'dashboard': 'finance', 'label': 'Expenses', 'model': 'account.move.line', 'fields': 'balance, account_id.account_type, parent_state, date', 'basis': 'flow', 'date_field': 'date', 'formula': 'SUM(balance) posted expense AML', 'group': 'account.group_account_readonly'},
            {'key': 'profit', 'dashboard': 'finance', 'label': 'Net result', 'model': 'account.move.line', 'fields': 'balance', 'basis': 'flow', 'date_field': 'date', 'formula': 'Revenue − expenses on posted AML', 'group': 'account.group_account_readonly'},
            {'key': 'cash', 'dashboard': 'finance', 'label': 'Cash & bank snapshot', 'model': 'account.move.line', 'fields': 'balance, account_id.account_type, date', 'basis': 'snapshot', 'date_field': 'date', 'formula': 'SUM(balance) asset_cash through date_to', 'group': 'account.group_account_readonly'},
            {'key': 'bank', 'dashboard': 'finance', 'label': 'Bank snapshot', 'model': 'account.move.line', 'fields': 'balance, journal_id.type', 'basis': 'snapshot', 'date_field': 'date', 'formula': 'asset_cash AML on bank journals', 'group': 'account.group_account_readonly'},
            {'key': 'cash_in_hand', 'dashboard': 'finance', 'label': 'Cash snapshot', 'model': 'account.move.line', 'fields': 'balance, journal_id.type', 'basis': 'snapshot', 'date_field': 'date', 'formula': 'asset_cash AML on cash journals', 'group': 'account.group_account_readonly'},
            {'key': 'inflow', 'dashboard': 'finance', 'label': 'Cash inflow', 'model': 'account.move.line', 'fields': 'debit', 'basis': 'flow', 'date_field': 'date', 'formula': 'SUM(debit) posted asset_cash', 'group': 'account.group_account_readonly'},
            {'key': 'outflow', 'dashboard': 'finance', 'label': 'Cash outflow', 'model': 'account.move.line', 'fields': 'credit', 'basis': 'flow', 'date_field': 'date', 'formula': 'SUM(credit) posted asset_cash', 'group': 'account.group_account_readonly'},
            {'key': 'receivables', 'dashboard': 'finance', 'label': 'Receivables', 'model': 'account.move', 'fields': 'amount_residual_signed, move_type, state', 'basis': 'snapshot', 'date_field': 'invoice_date_due', 'formula': 'SUM residual posted customer invoices', 'group': 'account.group_account_readonly'},
            {'key': 'overdue_ar', 'dashboard': 'finance', 'label': 'Overdue receivables', 'model': 'account.move', 'fields': 'invoice_date_due, payment_state, amount_residual_signed', 'basis': 'snapshot', 'date_field': 'invoice_date_due', 'formula': 'Residual unpaid/partial due before cutoff', 'group': 'account.group_account_readonly'},
            {'key': 'payables', 'dashboard': 'finance', 'label': 'Payables', 'model': 'account.move', 'fields': 'amount_residual_signed, move_type', 'basis': 'snapshot', 'date_field': 'invoice_date_due', 'formula': 'ABS residual posted vendor bills', 'group': 'account.group_account_readonly'},
            {'key': 'overdue_ap', 'dashboard': 'finance', 'label': 'Overdue payables', 'model': 'account.move', 'fields': 'invoice_date_due, payment_state', 'basis': 'snapshot', 'date_field': 'invoice_date_due', 'formula': 'ABS residual unpaid/partial vendor bills', 'group': 'account.group_account_readonly'},
            {'key': 'retention_ap', 'dashboard': 'finance', 'label': 'Vendor retention residual', 'model': 'account.move.line', 'fields': 'ages_is_vendor_retention_line, amount_residual', 'basis': 'snapshot', 'date_field': 'date', 'formula': 'ABS residual of vendor retention lines', 'group': 'account.group_account_readonly'},
            {'key': 'collections', 'dashboard': 'finance', 'label': 'Customer collections', 'model': 'account.payment', 'fields': 'payment_type, state, amount_company_currency_signed, is_internal_transfer', 'basis': 'flow', 'date_field': 'date', 'formula': 'ABS inbound paid/in_process excluding internal transfers', 'group': 'account.group_account_readonly'},
            {'key': 'vendor_payments', 'dashboard': 'finance', 'label': 'Vendor payments', 'model': 'account.payment', 'fields': 'payment_type, state, amount_company_currency_signed', 'basis': 'flow', 'date_field': 'date', 'formula': 'ABS outbound paid/in_process excluding internal transfers', 'group': 'account.group_account_readonly'},
            {'key': 'ms_opening', 'dashboard': 'finance', 'label': 'Main Summary opening', 'model': 'account.move.line', 'fields': 'MainSummaryEngine', 'basis': 'cash', 'date_field': 'date', 'formula': 'MainSummaryEngine opening', 'group': 'account.group_account_readonly'},
            {'key': 'ra_work', 'dashboard': 'contracts', 'label': 'RA work this period', 'model': 'ages.running.bill', 'fields': 'value_of_work_done, state, date', 'basis': 'flow', 'date_field': 'date', 'formula': 'SUM confirmed value_of_work_done in period', 'group': 'ages.contract read'},
            {'key': 'billed', 'dashboard': 'contracts', 'label': 'Cumulative RA work', 'model': 'ages.running.bill', 'fields': 'value_of_work_done, state', 'basis': 'snapshot', 'date_field': '', 'formula': "SUM value_of_work_done where state != cancelled", 'group': 'ages.contract read'},
            {'key': 'backlog', 'dashboard': 'contracts', 'label': 'Unbilled contract work', 'model': 'ages.contract', 'fields': 'total_work_done_value', 'basis': 'snapshot', 'date_field': '', 'formula': 'contract value − cumulative RA work', 'group': 'ages.contract read'},
            {'key': 'po_open', 'dashboard': 'procurement', 'label': 'PO not yet billed', 'model': 'purchase.order', 'fields': 'amount_untaxed, invoice_status, state', 'basis': 'commitment', 'date_field': '', 'formula': 'Confirmed PO untaxed where invoice_status in no/to invoice', 'group': 'purchase.group_purchase_user'},
            {'key': 'stock', 'dashboard': 'inventory', 'label': 'Inventory value', 'model': 'stock.valuation.layer', 'fields': 'value', 'basis': 'snapshot', 'date_field': '', 'formula': 'SUM stock.valuation.layer.value', 'group': 'stock.group_stock_user'},
            {'key': 'payroll', 'dashboard': 'payroll', 'label': 'Payroll net', 'model': 'hr.payslip', 'fields': 'net_wage, state, date_from', 'basis': 'flow', 'date_field': 'date_from', 'formula': 'SUM net_wage of done/paid payslips', 'group': 'ages_hr_payroll.group_hr_payroll_user'},
            {'key': 'leave_blocked', 'dashboard': 'payroll', 'label': 'Leave blocked from current payroll', 'model': 'hr.leave', 'fields': 'payslip_state', 'basis': 'count', 'date_field': 'date_from', 'formula': "COUNT hr.leave payslip_state=blocked", 'group': 'ages_hr_payroll.group_hr_payroll_user'},
            {'key': 'employees', 'dashboard': 'hr', 'label': 'Active employees', 'model': 'hr.employee', 'fields': 'active', 'basis': 'count', 'date_field': '', 'formula': 'COUNT active hr.employee', 'group': 'hr.group_hr_user'},
            {'key': 'att_hours', 'dashboard': 'attendance', 'label': 'Attendance hours', 'model': 'hr.attendance', 'fields': 'worked_hours, check_in', 'basis': 'count', 'date_field': 'check_in', 'formula': 'SUM worked_hours in period', 'group': 'hr.group_hr_user'},
            {'key': 'sales', 'dashboard': 'sales', 'label': 'Confirmed sales', 'model': 'sale.order', 'fields': 'amount_untaxed, state, date_order', 'basis': 'flow', 'date_field': 'date_order', 'formula': 'SUM amount_untaxed confirmed SO', 'group': 'sales_team.group_sale_salesman'},
            {'key': 'ordered', 'dashboard': 'partners', 'label': 'Customer ordered (SO)', 'model': 'sale.order', 'fields': 'amount_untaxed, state', 'basis': 'flow', 'date_field': 'date_order', 'formula': 'Confirmed SO untaxed in period', 'group': 'sales_team.group_sale_salesman'},
            {'key': 'working_capital', 'dashboard': 'finance', 'label': 'Cash + AR − AP', 'model': 'account.move', 'fields': 'amount_residual_signed', 'basis': 'snapshot', 'date_field': '', 'formula': 'cash snapshot + AR residual − AP residual', 'group': 'account.group_account_readonly'},
        ]

    def _unavailable_kpi(self, scope, key, label, reason, action_key=False):
        spec = self._action_specs().get(action_key) or {} if action_key else {}
        return {
            'key': key,
            'label': label,
            'value': False,
            'formatted': 'Unavailable',
            'previous': False,
            'previous_formatted': False,
            'delta': False,
            'percent': False,
            'direction': 'flat',
            'status': 'unavailable',
            'action_key': action_key,
            'tooltip': reason,
            'basis': 'unavailable',
            'date_field': spec.get('date_field') or '',
            'formula': reason,
            'unavailable': True,
            'model': spec.get('model') or '',
            'comparison_label': 'No comparison',
            'target_formatted': 'Target not configured',
        }

    def _group_chart(self, model_name, domain, groupby, title, chart_type='doughnut', value_field=False, invert=False, limit=12):
        if not self._can_read(model_name) or not self._field_path_exists(model_name, groupby):
            return self._chart(chart_type, title, [], [])
        if '.' in groupby:
            return self._related_group_chart(
                model_name, domain, groupby, title, chart_type, value_field, invert, limit
            )
        spec = ['%s:sum' % value_field] if value_field else ['id:count']
        try:
            rows = self.env[model_name].read_group(domain, spec, [groupby], lazy=False)
        except Exception as exc:
            _logger.warning('Dashboard group chart failed on %s.%s: %s', model_name, groupby, exc)
            return self._chart(chart_type, title, [], [])
        labels, data, extras = [], [], []
        for group in rows:
            raw = group.get(groupby)
            if isinstance(raw, (list, tuple)):
                name = raw[1] if raw else 'Unassigned'
                res_id = raw[0] if raw else False
            else:
                name = raw or 'Unassigned'
                res_id = False
            amount = group.get(value_field) if value_field else (group.get('%s_count' % groupby) or group.get('id_count') or 0)
            amount = amount or 0.0
            if invert:
                amount = -amount
            if value_field:
                amount = abs(amount)
            extras.append({'name': name, 'amount': amount, 'res_id': res_id})
        extras.sort(key=lambda item: item['amount'], reverse=True)
        extras = extras[:limit]
        labels = [item['name'] for item in extras]
        data = [round(item['amount'], 2) for item in extras]
        max_slices = 7 if chart_type in ('doughnut', 'pie') else 9
        return self._chart(
            chart_type, title, labels, [{'label': title, 'data': data}],
            group_field=groupby, label_ids=[item.get('res_id') for item in extras],
            max_slices=max_slices, unit='count' if not value_field else 'money',
        )

    def _related_group_chart(self, model_name, domain, groupby, title, chart_type='doughnut', value_field=False, invert=False, limit=12):
        parts = groupby.split('.')
        if len(parts) != 2 or not self._has_field(model_name, parts[0]):
            return self._chart(chart_type, title, [], [])
        first, second = parts
        comodel = self.env[model_name]._fields[first].comodel_name
        if not comodel or comodel not in self.env or not self._has_field(comodel, second):
            return self._chart(chart_type, title, [], [])
        spec = ['%s:sum' % value_field] if value_field else ['id:count']
        try:
            rows = self.env[model_name].read_group(domain, spec, [first], lazy=False)
        except Exception as exc:
            _logger.warning('Dashboard related group chart failed on %s.%s: %s', model_name, groupby, exc)
            return self._chart(chart_type, title, [], [])
        related_ids = [
            group.get(first)[0]
            for group in rows
            if isinstance(group.get(first), (list, tuple)) and group.get(first) and group.get(first)[0]
        ]
        related = {record.id: record for record in self.env[comodel].browse(related_ids).exists()}
        buckets = {}
        for group in rows:
            raw = group.get(first)
            rec_id = raw[0] if isinstance(raw, (list, tuple)) and raw else False
            record = related.get(rec_id)
            label = 'Unassigned'
            res_id = False
            if record is not None and second in record._fields:
                value = record[second]
                if isinstance(value, models.BaseModel):
                    label = value.display_name or 'Unassigned'
                    res_id = value.id or False
                elif value not in (None, False):
                    label = value
            amount = group.get(value_field) if value_field else (group.get('%s_count' % first) or group.get('id_count') or 0)
            amount = amount or 0.0
            if invert:
                amount = -amount
            if value_field:
                amount = abs(amount)
            bucket = buckets.setdefault(label, {'name': label, 'amount': 0.0, 'res_id': res_id})
            bucket['amount'] += amount
        extras = sorted(buckets.values(), key=lambda item: item['amount'], reverse=True)[:limit]
        return self._chart(
            chart_type, title,
            [item['name'] for item in extras],
            [{'label': title, 'data': [round(item['amount'], 2) for item in extras]}],
            group_field=groupby, label_ids=[item.get('res_id') for item in extras],
            max_slices=7 if chart_type in ('doughnut', 'pie') else 9,
            unit='count' if not value_field else 'money',
        )

    def _row_limit(self, scope, default=20):
        try:
            requested = int((scope or {}).get('limit') or default)
        except (TypeError, ValueError):
            requested = default
        return min(max(requested, 1), 100)

    def _document_rows(self, model_name, domain, field_map, action_key, limit=20, order=None, money_fields=(), date_fields=(), scope=None):
        if scope is not None:
            limit = self._row_limit(scope, limit)
        fields_list = list({name for name in field_map.values() if name} | {'id'})
        records = self._search_read(model_name, domain, fields_list, limit=limit, order=order)
        rows = []
        for rec in records:
            row = {'res_id': rec.get('id'), 'action_key': action_key}
            for column, fname in field_map.items():
                value = rec.get(fname)
                if isinstance(value, (list, tuple)):
                    value = value[1] if value else ''
                elif fname in date_fields:
                    value = self._format_date(value)
                elif fname in money_fields:
                    raw_amount = value or 0.0
                    row['%s_raw' % column] = raw_amount
                    value = self._format_money(raw_amount, scope or {})
                row[column] = value if value not in (None, False) else ''
            rows.append(row)
        return rows

    def _chart(self, chart_type, title, labels, datasets, stacked=False, action_key=False, group_field=False, label_ids=None, unit='count', size='md', subtitle='', variant='default', compare_labels=None, center_label='', max_slices=0, y_begin_at_zero=True, allow_toggle=False, why_key=False):
        labels = list(labels or [])
        datasets = list(datasets or [])
        label_ids = list(label_ids or [])
        if chart_type in ('doughnut', 'pie'):
            labels, datasets, label_ids = self._collapse_chart_tail(
                labels, datasets, label_ids, max_slices or 7
            )
        elif chart_type in ('bar', 'horizontalBar', 'stackedBar') and max_slices:
            labels, datasets, label_ids = self._collapse_chart_tail(
                labels, datasets, label_ids, max_slices
            )
        has_values = bool(labels) and any(
            any(value for value in (dataset.get('data') or []))
            for dataset in datasets
            if isinstance(dataset, dict)
        )
        is_ring = chart_type in ('doughnut', 'pie', 'gauge')
        return {
            'type': chart_type,
            'title': title,
            'labels': labels,
            'datasets': datasets,
            'stacked': stacked or chart_type == 'stackedBar',
            'action_key': action_key,
            'group_field': group_field,
            'label_ids': label_ids,
            'empty': (not labels) or (is_ring and not has_values),
            'unit': unit or 'count',
            'size': size or 'md',
            'subtitle': subtitle or '',
            'variant': variant or 'default',
            'compare_labels': compare_labels or [],
            'center_label': center_label or '',
            'max_slices': max_slices or 0,
            'y_begin_at_zero': bool(y_begin_at_zero),
            'allow_toggle': bool(allow_toggle) and chart_type in ('bar', 'line', 'area', 'mixed', 'stackedBar'),
            'why_key': why_key,
        }

    def _collapse_chart_tail(self, labels, datasets, label_ids, max_items):
        if len(labels) <= max_items:
            return labels, datasets, label_ids
        keep = max_items - 1
        new_labels = labels[:keep] + ['Other']
        new_datasets = []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            data = list(dataset.get('data') or [])
            head = data[:keep]
            tail = sum(float(value or 0.0) for value in data[keep:])
            item = dict(dataset)
            item['data'] = head + [round(tail, 2)]
            new_datasets.append(item)
        new_ids = list(label_ids[:keep]) if label_ids else []
        if new_ids:
            new_ids.append(False)
        return new_labels, new_datasets, new_ids

    def _waterfall_chart(self, labels, deltas, title, unit='money', size='lg', action_key=False):
        labels = list(labels or [])
        deltas = [float(value or 0.0) for value in (deltas or [])]
        base = []
        up = []
        down = []
        running = 0.0
        for value in deltas:
            if value >= 0:
                base.append(running)
                up.append(round(value, 2))
                down.append(0.0)
                running += value
            else:
                running += value
                base.append(running)
                up.append(0.0)
                down.append(round(abs(value), 2))
        return self._chart(
            'stackedBar', title, labels,
            [
                {'label': 'Base', 'data': [round(value, 2) for value in base], 'hidden': True},
                {'label': 'Increase', 'data': up},
                {'label': 'Decrease', 'data': down},
            ],
            stacked=True, unit=unit, size=size, variant='waterfall', action_key=action_key,
        )

    def _sparkline_from_chart(self, chart, dataset_index=0, unit='money'):
        if not chart or chart.get('empty'):
            return False
        datasets = chart.get('datasets') or []
        if dataset_index >= len(datasets):
            return False
        data = list((datasets[dataset_index] or {}).get('data') or [])
        if not any(float(value or 0.0) for value in data):
            return False
        return {
            'labels': list(chart.get('labels') or []),
            'data': data,
            'unit': unit or chart.get('unit') or 'money',
        }

    def _attach_sparklines(self, kpis, mapping):
        for kpi in kpis or []:
            spec = mapping.get(kpi.get('key'))
            if not spec or kpi.get('unavailable'):
                continue
            spark = self._sparkline_from_chart(spec[0], spec[1] if len(spec) > 1 else 0, spec[2] if len(spec) > 2 else 'money')
            if spark:
                kpi['sparkline'] = spark
        return kpis

    def _layout_section(self, section_id, section_type, keys=None, span=12, title='', hero=False, variant=''):
        item = {
            'id': section_id,
            'type': section_type,
            'keys': list(keys or []),
            'span': span,
        }
        if title:
            item['title'] = title
        if hero:
            item['hero'] = True
        if variant:
            item['variant'] = variant
        return item

    def _dashboard_layout(
        self, kind='standard', commentary=True, hero=None, alerts=None, charts=None,
        tables=None, quality=None, more=None, alert_title='Attention',
    ):
        sections = []
        if commentary and kind != 'executive':
            sections.append(self._layout_section('commentary', 'commentary', span=12))
        if hero:
            hero_variant = 'command' if kind == 'executive' else ''
            sections.append(self._layout_section(
                'hero', 'kpis', hero, 12, hero=True, variant=hero_variant,
            ))
        if alerts:
            alert_variant = 'briefing' if kind == 'executive' else ''
            sections.append(self._layout_section(
                'alerts', 'alerts', alerts, 12,
                title=alert_title or 'Attention',
                variant=alert_variant,
            ))
        chart_items = charts or []
        for index, item in enumerate(chart_items):
            if isinstance(item, dict):
                sections.append(item)
                continue
            if isinstance(item, (list, tuple)):
                key, span = item[0], item[1]
            else:
                span = 8 if index == 0 and len(chart_items) > 1 else (4 if index == 1 else 6)
                key = item
            sections.append(self._layout_section('chart_%s' % key, 'charts', [key], span))
        if quality:
            sections.append(self._layout_section('quality', 'quality', quality, 12, title='Data quality'))
        if tables:
            if kind == 'executive':
                sections.append(self._layout_section(
                    'watchlist', 'watchlist', tables, 12,
                    title='Watchlist', variant='watchlist',
                ))
            else:
                for key in tables:
                    sections.append(self._layout_section('table_%s' % key, 'tables', [key], 12))
        if more:
            sections.append(self._layout_section('more', 'more', more, 12, title='More indicators'))
        return {'kind': kind, 'sections': sections}

    def _mgmt_table(self, title, columns, rows, action_key=False, empty='No records in this scope.'):
        return {
            'title': title,
            'columns': columns,
            'rows': rows,
            'action_key': action_key,
            'empty': empty,
        }

    def _payload(self, scope, dashboard, kpis=None, charts=None, tables=None, alerts=None, extra=None, date_field='', warnings=None):
        currency = self._currency(scope)
        warnings = list(warnings or [])
        selected_companies = self.env['res.company'].with_context(button_access_skip=True).browse(
            [cid for cid in scope.get('company_ids', []) if cid]
        ).exists()
        source_currencies = selected_companies.mapped('currency_id')
        if source_currencies and any(item != currency for item in source_currencies):
            warnings.append(
                'Company-currency accounting amounts are converted to %s at each accounting date. '
                'Non-accounting document currencies are converted only by providers that expose a verified date/currency basis.'
                % currency.name
            )
        if [sid for sid in (scope.get('sub_company_ids') or []) if sid] or scope.get('include_unassigned'):
            warnings.append(
                'The active-company filter is applied only to models with a stored AGES sub-company path. '
                'Metrics without that dimension stay legal-company-wide and are not allocated.'
            )
        payload = {
            'meta': {
                'dashboard': dashboard,
                'generated_at': fields.Datetime.now().isoformat(),
                'date_from': str(scope.get('date_from') or ''),
                'date_to': str(scope.get('date_to') or ''),
                'date_field': date_field,
                'company_ids': scope.get('company_ids') or [],
                'sub_company_ids': [sid for sid in (scope.get('sub_company_ids') or []) if sid],
                'currency': {
                    'id': currency.id,
                    'name': currency.name,
                    'symbol': currency.symbol,
                },
                'scope_label': self._scope_label(scope),
                'comparison_label': self._comparison_label(scope),
                'warnings': warnings,
            },
            'kpis': kpis or [],
            'charts': charts or {},
            'tables': tables or {},
            'alerts': alerts or [],
            'commentary': self._factual_commentary(kpis),
        }
        if extra:
            payload.update(extra)
        if not payload.get('commentary'):
            payload['commentary'] = self._factual_commentary(kpis)
        layout = payload.get('layout') or {}
        if not layout.get('sections'):
            payload['layout'] = self._dashboard_layout(
                kind=layout.get('kind') or 'standard',
                hero=[kpi.get('key') for kpi in (kpis or [])[:5] if kpi.get('key')],
                charts=list((charts or {}).keys())[:4],
                tables=list((tables or {}).keys())[:2],
                alerts=[alert.get('key') for alert in (alerts or []) if alert.get('count')][:4],
                more=[kpi.get('key') for kpi in (kpis or [])[5:] if kpi.get('key')],
            )
        return payload

    def _scope_label(self, scope):
        date_from = scope.get('date_from')
        date_to = scope.get('date_to')
        period = scope.get('period')
        if period in ('ytd', 'year') and date_from:
            return '%s YTD' % date_from.year
        if date_from and date_to:
            return '%s – %s' % (self._format_date(date_from), self._format_date(date_to))
        if date_to:
            return 'Through %s' % self._format_date(date_to)
        return 'All time'

    def _unavailable(self, scope, dashboard, reason):
        return self._payload(
            scope,
            dashboard,
            warnings=[reason],
            extra={'available': False, 'reason': reason},
        )

    def _analytic_coverage(self, scope, date_from, date_to):
        coverage = self._coverage_ratio(
            'account.move.line',
            self._aml_posted_domain(scope) + self._date_domain('date', date_from, date_to),
            [('analytic_distribution', '!=', False)],
        )
        return coverage['percent'] if coverage else False

    def _coverage_ratio(self, model_name, domain, assigned_extra):
        if not self._can_read(model_name):
            return False
        total = self._search_count(model_name, domain)
        assigned = self._search_count(model_name, domain + list(assigned_extra or []))
        if not total:
            return {'total': 0, 'assigned': 0, 'missing': 0, 'percent': 100.0}
        return {
            'total': total,
            'assigned': assigned,
            'missing': max(total - assigned, 0),
            'percent': round(100.0 * assigned / float(total), 1),
        }

    def _payment_sum(self, scope, payment_type, date_from, date_to):
        if not self._can_read('account.payment'):
            return 0.0
        extra = [
            ('payment_type', '=', payment_type),
            ('state', 'in', ('paid', 'in_process')),
        ]
        if self._has_field('account.payment', 'is_internal_transfer'):
            extra.append(('is_internal_transfer', '=', False))
        domain = self._scope_domain('account.payment', scope, extra)
        domain += self._date_domain('date', date_from, date_to)
        field_name = 'amount_company_currency_signed' if self._has_field(
            'account.payment', 'amount_company_currency_signed'
        ) else 'amount'
        return abs(self._currency_sum(
            'account.payment', domain, field_name, scope,
            date_field='date',
            company_currency=(field_name == 'amount_company_currency_signed'),
        ) or 0.0)

    def _cash_bank_snapshot(self, scope, date_to):
        if not self._can_read('account.journal'):
            return 0.0, 0.0
        company_ids = [cid for cid in (scope.get('company_ids') or []) if cid] or self.env.companies.ids
        bank = cash = 0.0
        for journal_type in ('bank', 'cash'):
            journals = self.env['account.journal'].search([
                ('type', '=', journal_type),
                ('company_id', 'in', company_ids),
            ])
            if not journals:
                continue
            amount = self._aml_sum(scope, [
                ('account_id.account_type', '=', 'asset_cash'),
                ('journal_id', 'in', journals.ids),
            ], None, date_to)
            if journal_type == 'bank':
                bank = amount
            else:
                cash = amount
        return bank, cash

    def _aml_grouped(self, scope, extra, date_from, date_to, groupby, invert=False, limit=8):
        has_explicit_analytic_domain = any(
            isinstance(leaf, (list, tuple))
            and len(leaf) == 3
            and leaf[0] == 'analytic_distribution'
            for leaf in (extra or [])
        )
        if groupby == 'move_id.ages_project_id' and not has_explicit_analytic_domain:
            return self._analytic_project_rows(
                scope, extra, date_from, date_to, invert=invert, limit=limit
            )
        if '.' in groupby:
            move_field = groupby.split('.', 1)[1] if groupby.startswith('move_id.') else False
            if move_field and self._has_field('account.move', move_field):
                return self._aml_grouped_via_move(
                    scope, extra, date_from, date_to, move_field, invert=invert, limit=limit
                )
            return []
        if not self._can_read('account.move.line') or not self._field_path_exists('account.move.line', groupby):
            return []
        domain = self._aml_posted_domain(scope, extra) + self._date_domain('date', date_from, date_to)
        try:
            rows = self.env['account.move.line'].read_group(domain, ['balance:sum'], [groupby], lazy=False)
        except Exception as exc:
            _logger.warning('Dashboard AML group failed on %s: %s', groupby, exc)
            return []
        ranked = []
        for group in rows:
            raw = group.get(groupby)
            amount = group.get('balance') or 0.0
            if invert:
                amount = -amount
            if isinstance(raw, (list, tuple)):
                name = raw[1] if raw else 'Unassigned'
                res_id = raw[0] if raw else False
            else:
                name = raw or 'Unassigned'
                res_id = False
            ranked.append({
                'name': name,
                'amount': abs(amount),
                'formatted': self._format_money(abs(amount), scope),
                'res_id': res_id,
            })
        ranked.sort(key=lambda item: item['amount'], reverse=True)
        return ranked[:limit]

    def _aml_grouped_via_move(self, scope, extra, date_from, date_to, move_field, invert=False, limit=8):
        if not self._can_read('account.move.line') or not self._can_read('account.move'):
            return []
        domain = self._aml_posted_domain(scope, extra) + self._date_domain('date', date_from, date_to)
        try:
            rows = self.env['account.move.line'].read_group(domain, ['balance:sum'], ['move_id'], lazy=False)
        except Exception as exc:
            _logger.warning('Dashboard AML move group failed: %s', exc)
            return []
        move_ids = [
            row.get('move_id')[0]
            for row in rows
            if isinstance(row.get('move_id'), (list, tuple)) and row.get('move_id') and row.get('move_id')[0]
        ]
        moves = {move.id: move for move in self.env['account.move'].browse(move_ids).exists()}
        buckets = {}
        for row in rows:
            raw = row.get('move_id')
            move = moves.get(raw[0] if isinstance(raw, (list, tuple)) and raw else False)
            label = 'Unassigned'
            res_id = False
            if move and move_field in move._fields:
                value = move[move_field]
                if isinstance(value, models.BaseModel):
                    label = value.display_name or 'Unassigned'
                    res_id = value.id or False
                elif value not in (None, False):
                    label = value
            amount = row.get('balance') or 0.0
            if invert:
                amount = -amount
            bucket = buckets.setdefault(label, {'name': label, 'amount': 0.0, 'res_id': res_id})
            bucket['amount'] += abs(amount)
        ranked = sorted(buckets.values(), key=lambda item: item['amount'], reverse=True)[:limit]
        for item in ranked:
            item['formatted'] = self._format_money(item['amount'], scope)
        return ranked

    def _budget_line_model(self):
        if self._can_read('crossovered.budget.lines'):
            return 'crossovered.budget.lines'
        if self._can_read('crossovered.budget.line'):
            return 'crossovered.budget.line'
        return False

    def _po_line_values(self, scope, date_from=False, date_to=False):
        empty = {'ordered': 0.0, 'received': 0.0, 'billed': 0.0}
        if not self._can_read('purchase.order.line'):
            return empty
        domain = self._scope_domain('purchase.order.line', scope, [
            ('order_id.state', 'in', ('purchase', 'done')),
        ])
        date_path = self._first_date_field('purchase.order.line', ('date_order',)) or (
            'order_id.date_order' if self._field_path_exists('purchase.order.line', 'order_id.date_order') else False
        )
        if date_path and (date_from or date_to):
            domain += self._date_domain(date_path, date_from, date_to)
        fields_to_fetch = ['price_subtotal', 'product_qty', 'company_id']
        if self._has_field('purchase.order.line', 'date_order'):
            fields_to_fetch.append('date_order')
        elif self._field_path_exists('purchase.order.line', 'order_id.date_order'):
            fields_to_fetch.append('order_id')
        if self._has_field('purchase.order.line', 'qty_received'):
            fields_to_fetch.append('qty_received')
        if self._has_field('purchase.order.line', 'qty_invoiced'):
            fields_to_fetch.append('qty_invoiced')
        if self._has_field('purchase.order.line', 'currency_id'):
            fields_to_fetch.append('currency_id')
        lines = self.env['purchase.order.line'].search_fetch(domain, fields_to_fetch)
        ordered = received = billed = 0.0
        for line in lines:
            qty = line.product_qty or 0.0
            on_date = line.date_order if 'date_order' in line._fields else (
                line.order_id.date_order if 'order_id' in line._fields else scope.get('date_to')
            )
            amount = self._convert_amount(
                line.price_subtotal,
                line.currency_id if 'currency_id' in line._fields else line.company_id.currency_id,
                scope,
                on_date=on_date,
                company=line.company_id,
            )
            ordered += amount
            if qty:
                received += amount * ((getattr(line, 'qty_received', 0.0) or 0.0) / qty)
                billed += amount * ((getattr(line, 'qty_invoiced', 0.0) or 0.0) / qty)
        return {'ordered': ordered, 'received': received, 'billed': billed}

    def _pr_approval_hours(self, scope):
        if not (
            self._can_read('tier.review')
            and self._has_field('tier.review', 'reviewed_date')
            and self._can_read('purchase.request')
        ):
            return []
        requests = self.env['purchase.request'].search_fetch(
            self._scope_domain('purchase.request', scope, [('validation_status', '=', 'validated')]),
            ['create_date'],
        )
        if not requests:
            return []
        reviews = self.env['tier.review'].search([
            ('model', '=', 'purchase.request'),
            ('res_id', 'in', requests.ids),
            ('status', '=', 'approved'),
            ('reviewed_date', '!=', False),
        ])
        latest = {}
        for review in reviews:
            current = latest.get(review.res_id)
            if not current or review.reviewed_date > current:
                latest[review.res_id] = review.reviewed_date
        hours = []
        for request in requests:
            reviewed = latest.get(request.id)
            if not reviewed or not request.create_date:
                continue
            hours.append((reviewed - request.create_date).total_seconds() / 3600.0)
        return hours

    def _pr_average_approval_hours(self, scope):
        hours = self._pr_approval_hours(scope)
        if not hours:
            return None
        return round(sum(hours) / float(len(hours)), 1)

    def _elapsed_hours(self, start, stop):
        if not start or not stop:
            return False
        start = fields.Datetime.to_datetime(start)
        stop = fields.Datetime.to_datetime(stop)
        if not start or not stop:
            return False
        return max((stop - start).total_seconds() / 3600.0, 0.0)

    def _cycle_stats(self, hours):
        values = [item for item in hours if item not in (None, False)]
        if not values:
            return False
        ordered = sorted(values)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
        return {
            'count': len(ordered),
            'average': round(sum(ordered) / float(len(ordered)), 1),
            'median': round(median, 1),
            'longest': round(ordered[-1], 1),
        }

    def _scorecard(self, scope, key, label, actual, previous=False, action_key=False, kind='money', tooltip=''):
        kpi = self._kpi(
            scope, key, label, actual, previous, action_key, tooltip,
            suffix='' if kind != 'money' else False, basis='scorecard', kind=kind,
        )
        return {
            'key': key,
            'label': label,
            'actual': kpi['formatted'],
            'comparison': kpi['previous_formatted'],
            'percent': kpi['percent'],
            'target': kpi['target_formatted'],
            'status': kpi['target_status'],
            'direction': kpi['direction'],
            'action_key': action_key,
            'tooltip': tooltip,
        }

    def _factual_commentary(self, kpis):
        lines = []
        for kpi in kpis or []:
            if kpi.get('unavailable') or kpi.get('percent') in (None, False):
                continue
            direction = 'increased' if kpi.get('direction') == 'up' else (
                'decreased' if kpi.get('direction') == 'down' else 'was unchanged'
            )
            compare = kpi.get('comparison_label') or 'the previous period'
            if compare.startswith('vs '):
                compare = compare[3:]
            lines.append(
                '%s %s %s%% %s.'
                % (kpi.get('label'), direction, abs(round(kpi.get('percent') or 0.0, 1)), compare)
            )
            if len(lines) >= 3:
                break
        return lines

    def _budget_actual_rows(self, scope, limit=20):
        empty = {'planned': 0.0, 'actual': 0.0, 'variance': 0.0}
        line_model = self._budget_line_model()
        if not line_model or not self._has_field(line_model, 'practical_amount'):
            return [], empty, 'Budget actual (practical_amount) is not readable on a budget line.'
        domain = self._scope_domain(line_model, scope)
        if self._has_field(line_model, 'crossovered_budget_state'):
            domain += [('crossovered_budget_state', 'in', ('confirm', 'validate', 'done'))]
        date_from, date_to = scope.get('date_from'), scope.get('date_to')
        if date_from and self._has_field(line_model, 'date_to'):
            domain.append(('date_to', '>=', date_from))
        if date_to and self._has_field(line_model, 'date_from'):
            domain.append(('date_from', '<=', date_to))
        records = self.env[line_model].search(domain, limit=limit)
        rows = []
        planned_total = actual_total = 0.0
        for record in records:
            planned = record.planned_amount if self._has_field(line_model, 'planned_amount') else 0.0
            actual = record.practical_amount
            planned_total += planned or 0.0
            actual_total += actual or 0.0
            name = record.display_name
            if self._has_field(line_model, 'analytic_account_id') and record.analytic_account_id:
                name = record.analytic_account_id.display_name
            rows.append({
                'name': name,
                'planned': self._format_money(planned or 0.0, scope),
                'actual': self._format_money(actual or 0.0, scope),
                'variance': self._format_money((planned or 0.0) - (actual or 0.0), scope),
                'res_id': record.id,
                'action_key': 'budgets',
            })
        warning = ''
        if not self._field_is_stored(line_model, 'practical_amount'):
            warning = (
                'Budget actual uses computed practical_amount on browsed lines, not a SQL aggregate. '
                'The table is limited to the first %s overlapping lines.' % limit
            )
        return rows, {
            'planned': planned_total,
            'actual': actual_total,
            'variance': planned_total - actual_total,
        }, warning

    def _so_line_values(self, scope, date_from=False, date_to=False):
        empty = {'ordered': 0.0, 'delivered': 0.0, 'invoiced': 0.0}
        if not self._can_read('sale.order.line'):
            return empty
        domain = self._scope_domain('sale.order.line', scope, [
            ('order_id.state', 'in', ('sale', 'done')),
        ])
        if date_from or date_to:
            domain += self._date_domain('order_id.date_order' if self._field_path_exists('sale.order.line', 'order_id.date_order') else 'create_date', date_from, date_to)
        fields_to_fetch = ['price_subtotal', 'product_uom_qty', 'company_id']
        if self._has_field('sale.order.line', 'qty_delivered'):
            fields_to_fetch.append('qty_delivered')
        if self._has_field('sale.order.line', 'qty_invoiced'):
            fields_to_fetch.append('qty_invoiced')
        if self._has_field('sale.order.line', 'currency_id'):
            fields_to_fetch.append('currency_id')
        if self._field_path_exists('sale.order.line', 'order_id.date_order'):
            fields_to_fetch.append('order_id')
        lines = self.env['sale.order.line'].search_fetch(domain, fields_to_fetch)
        ordered = delivered = invoiced = 0.0
        for line in lines:
            qty = line.product_uom_qty or 0.0
            on_date = line.order_id.date_order if 'order_id' in fields_to_fetch else scope.get('date_to')
            amount = self._convert_amount(
                line.price_subtotal,
                line.currency_id if 'currency_id' in line._fields else line.company_id.currency_id,
                scope,
                on_date=on_date,
                company=line.company_id,
            )
            ordered += amount
            if qty:
                delivered += amount * ((getattr(line, 'qty_delivered', 0.0) or 0.0) / qty)
                invoiced += amount * ((getattr(line, 'qty_invoiced', 0.0) or 0.0) / qty)
        return {'ordered': ordered, 'delivered': delivered, 'invoiced': invoiced}

    def _procurement_cycle_times(self, scope):
        result = {
            'pr_approval': self._cycle_stats(self._pr_approval_hours(scope)),
            'pr_to_po': False,
            'po_to_receipt': False,
        }
        hours = []
        if (
            self._can_read('purchase.request.line')
            and self._has_field('purchase.request.line', 'purchase_lines')
            and self._can_read('purchase.order')
        ):
            lines = self.env['purchase.request.line'].search(
                self._scope_domain('purchase.request.line', scope, [('purchase_lines', '!=', False)]),
                limit=200,
            )
            for line in lines:
                request_date = line.request_id.create_date if line.request_id else False
                orders = line.purchase_lines.mapped('order_id').filtered(lambda order: order.state in ('purchase', 'done') and order.date_order)
                for order in orders:
                    hours.append(self._elapsed_hours(request_date, order.date_order))
            result['pr_to_po'] = self._cycle_stats(hours)
        receipt_hours = []
        if self._can_read('stock.move') and self._has_field('stock.move', 'purchase_line_id'):
            move_date = 'actual_date' if self._has_field('stock.move', 'actual_date') else 'date'
            moves = self.env['stock.move'].search_fetch(
                self._scope_domain('stock.move', scope, [
                    ('purchase_line_id', '!=', False),
                    ('state', '=', 'done'),
                ]),
                ['purchase_line_id', move_date],
                limit=400,
            )
            for move in moves:
                po_date = move.purchase_line_id.order_id.date_order if move.purchase_line_id and move.purchase_line_id.order_id else False
                done_date = getattr(move, move_date, False)
                receipt_hours.append(self._elapsed_hours(po_date, done_date))
            result['po_to_receipt'] = self._cycle_stats(receipt_hours)
        return result

    def _svl_gl_warning(self, scope):
        if not self._can_read('stock.valuation.layer') or not self._can_read('account.move.line'):
            return False
        svl = self._read_group_sum(
            'stock.valuation.layer', self._scope_domain('stock.valuation.layer', scope), 'value',
        ) or 0.0
        gl = self._aml_sum(scope, [
            ('account_id.account_type', '=', 'asset_current'),
            ('account_id.reconcile', '=', False),
        ], None, scope.get('date_to'))
        return (
            'SVL remaining value is %s. Current-asset AML (broad proxy, not a hardcoded stock account) is %s. '
            'These are not forced equal; investigate only when the business stock valuation accounts are reviewed.'
            % (self._format_money(svl, scope), self._format_money(gl or 0.0, scope))
        )

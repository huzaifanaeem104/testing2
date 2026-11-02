# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models
from odoo.osv import expression

from .helpers import PERIOD_PRESETS


class AgesEnterpriseDashboardContext(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def _accessible_ids(self, model_name, value, domain=None):
        ids = self._id_list(value)
        if not ids or not self._can_read(model_name):
            return []
        valid_domain = []
        for leaf in domain or []:
            if (
                isinstance(leaf, (list, tuple))
                and len(leaf) == 3
                and self._field_path_exists(model_name, leaf[0])
            ):
                valid_domain.append(tuple(leaf))
        accessible = set(self.env[model_name].search(
            expression.AND([[('id', 'in', ids)], valid_domain])
        ).ids)
        return [record_id for record_id in ids if record_id in accessible]

    def _string_list(self, value):
        values = value if isinstance(value, (list, tuple, set)) else [value]
        return [item for item in values if isinstance(item, str) and item]

    def _safe_int(self, value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _previous_year_dates(self, date_from, date_to):
        def shift(value):
            if not value:
                return False
            try:
                return value.replace(year=value.year - 1)
            except ValueError:
                return value.replace(year=value.year - 1, day=28)
        return shift(date_from), shift(date_to)

    def _dates_for_preset(self, preset, today):
        if preset == 'today':
            return today, today
        if preset == 'yesterday':
            day = today - timedelta(days=1)
            return day, day
        if preset == 'week':
            start = today - timedelta(days=today.weekday())
            return start, today
        if preset == 'month':
            return today.replace(day=1), today
        if preset == 'last_month':
            previous_end = today.replace(day=1) - timedelta(days=1)
            return previous_end.replace(day=1), previous_end
        if preset == 'quarter':
            first_month = ((today.month - 1) // 3) * 3 + 1
            return today.replace(month=first_month, day=1), today
        if preset in ('year', 'ytd'):
            return today.replace(month=1, day=1), today
        if preset == 'previous_year':
            start = today.replace(year=today.year - 1, month=1, day=1)
            end = today.replace(year=today.year - 1, month=12, day=31)
            return start, end
        return False

    def _normalize_filters(self, filters=None):
        raw = dict(filters or {})
        allowed_ids = list(self.env.companies.ids)
        requested = self._id_list(raw.get('company_ids') if 'company_ids' in raw else raw.get('company_id'))
        company_ids = [cid for cid in requested if cid in allowed_ids] if requested else allowed_ids
        if requested and not company_ids:
            company_ids = [0]

        today = fields.Date.context_today(self)
        period = raw.get('period') or 'month'
        if period not in dict(PERIOD_PRESETS) and period != 'year':
            period = 'month'
        computed = self._dates_for_preset(period, today)
        if computed:
            date_from, date_to = computed
        else:
            date_to = fields.Date.to_date(raw.get('date_to')) or today
            date_from = fields.Date.to_date(raw.get('date_from')) or date_to.replace(day=1)
            period = 'custom'
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        compare_period = raw.get('compare_period') or 'previous_period'
        if compare_period not in ('previous_period', 'previous_year', 'none'):
            compare_period = 'previous_period'
        if compare_period == 'previous_year' or (
            compare_period == 'previous_period' and period in ('year', 'ytd')
        ):
            previous_from, previous_to = self._previous_year_dates(date_from, date_to)
        elif compare_period == 'none':
            previous_from = previous_to = False
        elif date_from:
            span = (date_to - date_from).days
            previous_to = date_from - timedelta(days=1)
            previous_from = previous_to - timedelta(days=span)
        else:
            previous_from = previous_to = False

        sub_company_ids = self._id_list(
            raw.get('sub_company_ids') if 'sub_company_ids' in raw else raw.get('sub_company_id'),
            allow_zero=True,
        )
        real_sub_ids = [sid for sid in sub_company_ids if sid]
        if real_sub_ids and self._can_read('ages.sub.company'):
            valid = self.env['ages.sub.company'].search([
                ('id', 'in', real_sub_ids),
                ('company_id', 'in', [cid for cid in company_ids if cid] or allowed_ids),
            ]).ids
            sub_company_ids = [sid for sid in sub_company_ids if sid == 0 or sid in valid]

        project_ids = None
        raw_projects = raw.get('project_ids') if 'project_ids' in raw else raw.get('project_id')
        if raw_projects not in (None, False, '', [], ()):
            project_ids = self._id_list(raw_projects)
            if not project_ids:
                project_ids = None
            elif self._can_read('project.project'):
                project_ids = self.env['project.project'].search([
                    ('id', 'in', project_ids),
                    ('company_id', 'in', [cid for cid in company_ids if cid] or allowed_ids),
                ]).ids

        company_domain = [('company_id', 'in', [cid for cid in company_ids if cid] or allowed_ids)]
        contract_ids = self._accessible_ids(
            'ages.contract',
            raw.get('contract_ids') if 'contract_ids' in raw else raw.get('contract_id'),
            company_domain,
        )
        partner_ids = self._accessible_ids(
            'res.partner',
            raw.get('partner_ids') if 'partner_ids' in raw else raw.get('partner_id'),
        )
        vendor_ids = self._accessible_ids(
            'res.partner',
            raw.get('vendor_ids') if 'vendor_ids' in raw else raw.get('vendor_id'),
        )
        department_ids = self._accessible_ids(
            'hr.department',
            raw.get('department_ids') if 'department_ids' in raw else raw.get('department_id'),
        )
        warehouse_ids = self._accessible_ids(
            'stock.warehouse',
            raw.get('warehouse_ids') if 'warehouse_ids' in raw else raw.get('warehouse_id'),
            company_domain,
        )
        employee_ids = self._accessible_ids(
            'hr.employee',
            raw.get('employee_ids') if 'employee_ids' in raw else raw.get('employee_id'),
            company_domain,
        )
        product_ids = self._accessible_ids(
            'product.product',
            raw.get('product_ids') if 'product_ids' in raw else raw.get('product_id'),
        )
        product_category_ids = self._accessible_ids(
            'product.category',
            raw.get('product_category_ids') if 'product_category_ids' in raw else raw.get('product_category_id'),
        )
        location_ids = self._accessible_ids(
            'stock.location',
            raw.get('location_ids') if 'location_ids' in raw else raw.get('location_id'),
        )
        journal_ids = self._accessible_ids(
            'account.journal',
            raw.get('journal_ids') if 'journal_ids' in raw else raw.get('journal_id'),
            company_domain,
        )
        account_ids = self._accessible_ids(
            'account.account',
            raw.get('account_ids') if 'account_ids' in raw else raw.get('account_id'),
            company_domain,
        )
        analytic_account_ids = self._accessible_ids(
            'account.analytic.account',
            raw.get('analytic_account_ids') if 'analytic_account_ids' in raw else raw.get('analytic_account_id'),
            company_domain,
        )
        salesperson_ids = self._accessible_ids(
            'res.users',
            raw.get('salesperson_ids') if 'salesperson_ids' in raw else raw.get('salesperson_id'),
        )
        sales_team_ids = self._accessible_ids(
            'crm.team',
            raw.get('sales_team_ids') if 'sales_team_ids' in raw else raw.get('sales_team_id'),
        )
        requester_ids = self._accessible_ids(
            'res.users',
            raw.get('requester_ids') if 'requester_ids' in raw else raw.get('requester_id'),
        )
        currency_ids = self._accessible_ids(
            'res.currency',
            raw.get('currency_ids') if 'currency_ids' in raw else raw.get('currency_id'),
            [('active', '=', True)],
        )
        reporting_currency_ids = self._accessible_ids(
            'res.currency',
            raw.get('reporting_currency_id'),
            [('active', '=', True)],
        )
        approval_statuses = self._string_list(
            raw.get('approval_statuses') if 'approval_statuses' in raw else raw.get('approval_status')
        )
        document_statuses = self._string_list(
            raw.get('document_statuses') if 'document_statuses' in raw else raw.get('document_status')
        )
        labour_categories = [
            value for value in self._string_list(
                raw.get('labour_categories') if 'labour_categories' in raw else raw.get('labour_category')
            ) if value in ('staff', 'site', 'labor')
        ]

        return {
            'period': period,
            'compare_period': compare_period,
            'date_from': date_from,
            'date_to': date_to,
            'previous_from': previous_from,
            'previous_to': previous_to,
            'company_ids': company_ids,
            'sub_company_ids': sub_company_ids,
            'include_unassigned': 0 in sub_company_ids,
            'project_ids': project_ids,
            'contract_ids': contract_ids,
            'partner_ids': partner_ids,
            'vendor_ids': vendor_ids,
            'department_ids': department_ids,
            'warehouse_ids': warehouse_ids,
            'employee_ids': employee_ids,
            'product_ids': product_ids,
            'product_category_ids': product_category_ids,
            'location_ids': location_ids,
            'journal_ids': journal_ids,
            'account_ids': account_ids,
            'analytic_account_ids': analytic_account_ids,
            'salesperson_ids': salesperson_ids,
            'sales_team_ids': sales_team_ids,
            'requester_ids': requester_ids,
            'approval_statuses': approval_statuses,
            'document_statuses': document_statuses,
            'labour_categories': labour_categories,
            'currency_ids': currency_ids,
            'reporting_currency_id': reporting_currency_ids[0] if reporting_currency_ids else False,
            'dashboard': raw.get('dashboard') or 'executive',
            'limit': min(max(self._safe_int(raw.get('limit'), 20), 1), 100),
            'offset': max(self._safe_int(raw.get('offset'), 0), 0),
        }

    def _capability_map(self):
        account_access = self._user_in_any_group(
            'account.group_account_readonly',
            'account.group_account_invoice',
            'account.group_account_user',
            'account.group_account_manager',
        )
        project_access = self._user_in_any_group(
            'project.group_project_user',
            'project.group_project_manager',
        )
        purchase_access = self._user_in_any_group(
            'purchase.group_purchase_user',
            'purchase.group_purchase_manager',
        )
        purchase_request_access = self._user_in_any_group(
            'purchase_request.group_purchase_request_user',
            'purchase_request.group_purchase_request_manager',
        )
        stock_access = self._user_in_any_group(
            'stock.group_stock_user',
            'stock.group_stock_manager',
        )
        hr_access = self._user_in_any_group(
            'hr.group_hr_user',
            'hr.group_hr_manager',
        )
        sale_access = self._user_in_any_group(
            'sales_team.group_sale_salesman',
            'sales_team.group_sale_manager',
        )
        return {
            'account': self._can_read('account.move') and account_access,
            'analytic': self._can_read('account.analytic.account'),
            'project': self._can_read('project.project') and project_access,
            'contract': self._can_read('ages.contract'),
            'running_bill': self._can_read('ages.running.bill'),
            'mobilization': self._can_read('ages.mobilization.advance'),
            'retention': self._can_read('ages.retention.recovery'),
            'purchase': self._can_read('purchase.order') and purchase_access,
            'purchase_request': self._can_read('purchase.request') and purchase_request_access,
            'stock': self._can_read('stock.quant') and stock_access,
            'stock_valuation': self._can_read('stock.valuation.layer'),
            'gate_pass': self._can_read('ages.gate.pass'),
            'material_consumption': self._can_read('ages.material.consumption'),
            'ages_expense': self._can_read('ages.expense'),
            'hr_expense': self._can_read('hr.expense'),
            'hr': self._can_read('hr.employee') and hr_access,
            'payroll': self._can_read('hr.payslip') and (
                self._user_in_group('ages_hr_payroll.group_hr_payroll_user')
                or self._user_in_group('ages_hr_payroll.group_hr_payroll_manager')
            ),
            'attendance': self._can_read('hr.attendance'),
            'work_entry': self._can_read('hr.work.entry'),
            'portal_attendance': self._can_read('project.portal.attendance'),
            'sale': self._can_read('sale.order') and sale_access,
            'asset_oca': self._can_read('account.asset'),
            'asset_om': self._can_read('account.asset.asset'),
            'asset_transfer': self._can_read('asset.transfer'),
            'tier': self._can_read('tier.review'),
            'crm': self._can_read('crm.lead'),
            'mrp': self._can_read('mrp.production'),
            'quality': self._can_read('quality.check'),
            'construction': self._can_read('construction.boq'),
            'presence': self._can_read('ages.user.session') and self._user_in_group('ages_user_presence.group_presence_monitor'),
            'audit': self._can_read('ages.deletion.audit') and self._user_in_group('ages_deletion_audit.group_deletion_audit_viewer'),
            'budget': self._can_read('crossovered.budget') or self._can_read('crossovered.budget.lines') or self._can_read('crossovered.budget.line'),
        }

    def _dashboard_item(self, key, label, icon, available, reason=''):
        return {
            'key': key,
            'label': label,
            'icon': icon,
            'available': bool(available),
            'reason': '' if available else (
                reason or 'This dashboard is not installed or not authorized for your user.'
            ),
        }

    def _dashboard_catalog(self):
        caps = self._capability_map()
        item = self._dashboard_item
        return [
            item('executive', 'Executive Overview', 'fa-gauge-high', True),
            item('action_center', 'Action Center', 'fa-bolt', True),
            item('finance', 'Accounting & Finance', 'fa-scale-balanced', caps['account'], 'Accounting is not authorized for your user.'),
            item('contracts', 'Contracts & RA Billing', 'fa-file-contract', caps['contract'], 'AGES contracts are not installed or not authorized.'),
            item('projects', 'Projects', 'fa-diagram-project', caps['project'], 'Projects are not authorized for your user.'),
            item('procurement', 'Procurement & Purchase', 'fa-cart-shopping', caps['purchase'] or caps['purchase_request'], 'Purchase is not authorized for your user.'),
            item('inventory', 'Inventory & Site Logistics', 'fa-boxes-stacked', caps['stock'], 'Inventory is not authorized for your user.'),
            item('expenses', 'Expenses', 'fa-receipt', caps['ages_expense'] or caps['hr_expense'], 'Expense modules are not installed or not authorized.'),
            item('hr', 'Human Resources', 'fa-users', caps['hr'], 'HR is not authorized for your user.'),
            item('payroll', 'Payroll', 'fa-money-check-dollar', caps['payroll'], 'Payroll is hidden unless you have AGES payroll access and payslip read rights.'),
            item('attendance', 'Attendance', 'fa-clock', caps['attendance'] or caps['portal_attendance'], 'Attendance is not authorized for your user.'),
            item('sales', 'Sales', 'fa-chart-line', caps['sale'], 'Sales is not authorized for your user.'),
            item(
                'partners', 'Customer & Vendor 360', 'fa-address-book',
                caps['sale'] or caps['purchase'] or caps['account'] or caps['contract'],
                'Sale, purchase, accounting, or contract access is required.',
            ),
            item('assets', 'Assets', 'fa-building', caps['asset_oca'] or caps['asset_om'], 'Asset modules are not installed or not authorized.'),
            item('governance', 'Governance & Approvals', 'fa-shield-halved', caps['tier'] or caps['account'], 'Governance data is not authorized for your user.'),
            item('quality_data', 'Data Quality', 'fa-database', True),
            item('manufacturing', 'Manufacturing', 'fa-industry', caps['mrp'], 'Manufacturing is not installed or not authorized.'),
            item('crm', 'CRM', 'fa-handshake', caps['crm'], 'CRM is not installed or not authorized.'),
            item('construction', 'Construction Pro', 'fa-helmet-safety', caps['construction'], 'Construction Pro is not installed or not authorized.'),
            item('quality', 'Quality', 'fa-clipboard-check', caps['quality'], 'Quality is not installed or not authorized.'),
            item('system', 'System Activity', 'fa-user-clock', caps['presence'] or caps['audit'], 'System activity requires presence monitoring or deletion-audit access.'),
        ]

    def _filter_catalog(self):
        return {
            'executive': ['company', 'sub_company', 'project', 'contract', 'currency'],
            'action_center': ['company', 'sub_company', 'project', 'approval_status', 'document_status'],
            'finance': [
                'company', 'sub_company', 'project', 'contract', 'journal',
                'account', 'analytic_account', 'currency',
            ],
            'contracts': ['company', 'sub_company', 'project', 'contract', 'partner'],
            'projects': ['company', 'sub_company', 'project', 'department', 'analytic_account'],
            'procurement': [
                'company', 'sub_company', 'project', 'vendor', 'warehouse',
                'product', 'product_category', 'requester', 'approval_status',
                'document_status', 'currency',
            ],
            'inventory': [
                'company', 'sub_company', 'project', 'warehouse', 'location',
                'product', 'product_category', 'document_status',
            ],
            'expenses': [
                'company', 'sub_company', 'project', 'vendor', 'journal',
                'account', 'analytic_account', 'document_status', 'currency',
            ],
            'hr': ['company', 'department', 'employee', 'project', 'labour_category', 'document_status'],
            'payroll': [
                'company', 'department', 'employee', 'project',
                'analytic_account', 'document_status', 'currency',
            ],
            'attendance': ['company', 'department', 'employee', 'project', 'labour_category', 'document_status'],
            'sales': [
                'company', 'partner', 'project', 'product', 'product_category',
                'salesperson', 'sales_team', 'document_status', 'currency',
            ],
            'partners': ['company', 'partner', 'vendor', 'contract', 'project', 'employee'],
            'assets': ['company', 'project', 'location', 'document_status', 'currency'],
            'governance': ['company', 'approval_status', 'document_status'],
            'quality_data': ['company', 'project'],
            'manufacturing': ['company', 'project', 'product', 'document_status'],
            'crm': ['company', 'partner', 'salesperson', 'sales_team', 'document_status', 'currency'],
            'construction': ['company', 'project'],
            'quality': ['company', 'warehouse', 'product', 'product_category'],
            'system': ['company'],
        }

    def _role_default_dashboard(self):
        caps = self._capability_map()
        if caps.get('account'):
            return 'executive'
        if caps.get('project'):
            return 'projects'
        if caps.get('purchase') or caps.get('purchase_request'):
            return 'procurement'
        if caps.get('stock'):
            return 'inventory'
        if caps.get('hr'):
            return 'hr'
        return 'action_center'

    @api.model
    def get_dashboard_context(self, filters=None):
        scope = self._normalize_filters(filters)
        catalog = self._dashboard_catalog()
        return {
            'dashboards': catalog,
            'capabilities': self._capability_map(),
            'periods': [{'key': key, 'label': label} for key, label in PERIOD_PRESETS],
            'compare_periods': [
                {'key': 'previous_period', 'label': 'Previous period'},
                {'key': 'previous_year', 'label': 'Previous year'},
                {'key': 'none', 'label': 'No comparison'},
            ],
            'default_dashboard': self._role_default_dashboard(),
            'filter_catalog': self._filter_catalog(),
            'kpi_registry': self._kpi_registry_summary(),
            'scope': {
                'date_from': str(scope['date_from'] or ''),
                'date_to': str(scope['date_to'] or ''),
                'period': scope['period'],
                'compare_period': scope['compare_period'],
            },
        }

    def _selection_options(self, model_name, field_name):
        if not self._has_field(model_name, field_name):
            return []
        try:
            selection = self.env[model_name]._fields[field_name]._description_selection(self.env)
        except Exception:
            return []
        return [{'id': key, 'name': label} for key, label in selection]

    def _document_status_options(self, dashboard):
        model_map = {
            'action_center': ('account.move', 'purchase.request', 'stock.picking'),
            'contracts': ('ages.contract', 'ages.running.bill'),
            'projects': ('project.project', 'project.task'),
            'procurement': ('purchase.request', 'purchase.order'),
            'inventory': ('stock.picking', 'ages.gate.pass', 'ages.material.consumption'),
            'expenses': ('ages.expense', 'hr.expense'),
            'hr': ('hr.contract', 'hr.leave'),
            'payroll': ('hr.payslip', 'hr.payslip.run'),
            'attendance': ('hr.work.entry', 'project.portal.attendance'),
            'sales': ('sale.order',),
            'assets': ('account.asset', 'account.asset.asset', 'asset.transfer'),
            'governance': ('account.move',),
            'manufacturing': ('mrp.production',),
            'crm': ('crm.lead',),
        }
        options = {}
        for model_name in model_map.get(dashboard, ()):
            for item in self._selection_options(model_name, 'state'):
                options.setdefault(item['id'], item['name'])
        return [{'id': key, 'name': label} for key, label in options.items()]

    def _filter_kind_needed(self, scope, *kinds):
        catalog = set(self._filter_catalog().get(scope.get('dashboard') or 'executive') or [])
        catalog.update(('company', 'sub_company'))
        return any(kind in catalog for kind in kinds)

    def _search_filter_records(self, model_name, domain, limit=40, order='name', query=''):
        if not self._can_read(model_name):
            return []
        if query:
            name_field = 'complete_name' if 'complete_name' in self.env[model_name]._fields else 'name'
            if name_field in self.env[model_name]._fields:
                domain = list(domain or []) + [(name_field, 'ilike', query)]
        records = self.env[model_name].search(domain or [], limit=min(max(int(limit or 40), 1), 80), order=order)
        return [{'id': rec.id, 'name': rec.display_name} for rec in records]

    @api.model
    def get_filter_options(self, filters=None):
        scope = self._normalize_filters(filters)
        needed = set(self._filter_catalog().get(scope.get('dashboard') or 'executive') or [])
        needed.update(('company', 'sub_company'))
        companies = [{'id': company.id, 'name': company.name} for company in self.env.companies]
        sub_companies = []
        if 'sub_company' in needed and self._can_read('ages.sub.company'):
            records = self.env['ages.sub.company'].search([
                ('company_id', 'in', [cid for cid in scope['company_ids'] if cid] or self.env.companies.ids),
            ])
            sub_companies = [{'id': rec.id, 'name': rec.name} for rec in records]
        company_ids = [cid for cid in scope['company_ids'] if cid] or self.env.companies.ids
        options = {
            'companies': companies,
            'sub_companies': sub_companies,
            'projects': [],
            'contracts': [],
            'partners': [],
            'vendors': [],
            'departments': [],
            'warehouses': [],
            'employees': [],
            'products': [],
            'product_categories': [],
            'locations': [],
            'journals': [],
            'accounts': [],
            'analytic_accounts': [],
            'salespersons': [],
            'sales_teams': [],
            'requesters': [],
            'approval_statuses': [],
            'document_statuses': [],
            'labour_categories': [],
            'currencies': [],
        }
        if 'project' in needed:
            options['projects'] = self._search_filter_records(
                'project.project',
                self._company_domain('project.project', scope) + [('active', '=', True)],
                limit=80,
            )
        if 'contract' in needed:
            options['contracts'] = self._search_filter_records(
                'ages.contract', self._company_domain('ages.contract', scope), limit=80, order='name desc',
            )
        if 'partner' in needed:
            options['partners'] = self._search_filter_records(
                'res.partner', [('customer_rank', '>', 0)], limit=40,
            )
        if 'vendor' in needed:
            options['vendors'] = self._search_filter_records(
                'res.partner', [('supplier_rank', '>', 0)], limit=40,
            )
        if 'department' in needed:
            options['departments'] = self._search_filter_records('hr.department', [], limit=40)
        if 'warehouse' in needed:
            options['warehouses'] = self._search_filter_records(
                'stock.warehouse', [('company_id', 'in', self.env.companies.ids)], limit=40,
            )
        if 'employee' in needed:
            options['employees'] = self._search_filter_records(
                'hr.employee', self._company_domain('hr.employee', scope) + [('active', '=', True)], limit=40,
            )
        if 'product' in needed:
            options['products'] = self._search_filter_records(
                'product.product', [('active', '=', True)], limit=40,
            )
        if 'product_category' in needed:
            options['product_categories'] = self._search_filter_records(
                'product.category', [], limit=40, order='complete_name',
            )
        if 'location' in needed:
            location_domain = [('usage', 'in', ('internal', 'transit'))]
            if self._has_field('stock.location', 'company_id'):
                location_domain.append(('company_id', 'in', [False] + company_ids))
            options['locations'] = self._search_filter_records(
                'stock.location', location_domain, limit=40, order='complete_name',
            )
        if 'journal' in needed:
            options['journals'] = self._search_filter_records(
                'account.journal', [('company_id', 'in', company_ids)], limit=40,
            )
        if 'account' in needed:
            options['accounts'] = self._search_filter_records(
                'account.account', [], limit=40, order='code',
            )
        if 'analytic_account' in needed:
            analytic_domain = []
            if self._has_field('account.analytic.account', 'company_id'):
                analytic_domain = [('company_id', 'in', [False] + company_ids)]
            options['analytic_accounts'] = self._search_filter_records(
                'account.analytic.account', analytic_domain, limit=40,
            )
        if needed.intersection(('salesperson', 'requester')) and self._can_read('res.users'):
            users = self._search_filter_records(
                'res.users', [('active', '=', True), ('share', '=', False)], limit=40,
            )
            if 'salesperson' in needed:
                options['salespersons'] = users
            if 'requester' in needed:
                options['requesters'] = users
        if 'sales_team' in needed:
            options['sales_teams'] = self._search_filter_records(
                'crm.team', [('active', '=', True)], limit=40,
            )
        if 'currency' in needed:
            options['currencies'] = self._search_filter_records(
                'res.currency', [('active', '=', True)], limit=40,
            )
        if 'approval_status' in needed:
            approval_options = {}
            for model_name in ('purchase.request', 'account.payment'):
                for item in self._selection_options(model_name, 'validation_status'):
                    approval_options.setdefault(item['id'], item['name'])
            for item in self._selection_options('tier.review', 'status'):
                approval_options.setdefault(item['id'], item['name'])
            options['approval_statuses'] = [
                {'id': key, 'name': label} for key, label in approval_options.items()
            ]
        if 'document_status' in needed and scope.get('dashboard') not in ('executive', 'finance'):
            options['document_statuses'] = self._document_status_options(scope.get('dashboard'))
        if 'labour_category' in needed:
            options['labour_categories'] = self._selection_options('hr.employee', 'ages_employee_category')
        return options

    @api.model
    def get_filter_search(self, kind, query, filters=None):
        scope = self._normalize_filters(filters)
        catalog = self._filter_catalog().get(scope.get('dashboard') or 'executive') or []
        if kind not in catalog:
            return []
        query = (query or '').strip()
        company_ids = [cid for cid in scope['company_ids'] if cid] or self.env.companies.ids
        specs = {
            'project': ('project.project', self._company_domain('project.project', scope) + [('active', '=', True)]),
            'contract': ('ages.contract', self._company_domain('ages.contract', scope)),
            'partner': ('res.partner', [('customer_rank', '>', 0)]),
            'vendor': ('res.partner', [('supplier_rank', '>', 0)]),
            'employee': ('hr.employee', self._company_domain('hr.employee', scope) + [('active', '=', True)]),
            'product': ('product.product', [('active', '=', True)]),
            'account': ('account.account', []),
            'analytic_account': (
                'account.analytic.account',
                [('company_id', 'in', [False] + company_ids)] if self._has_field('account.analytic.account', 'company_id') else [],
            ),
            'journal': ('account.journal', [('company_id', 'in', company_ids)]),
            'location': (
                'stock.location',
                [('usage', 'in', ('internal', 'transit'))] + (
                    [('company_id', 'in', [False] + company_ids)] if self._has_field('stock.location', 'company_id') else []
                ),
            ),
        }
        spec = specs.get(kind)
        if not spec:
            return []
        return self._search_filter_records(spec[0], spec[1], limit=40, query=query)

    @api.model
    def get_dashboard(self, dashboard_key, filters=None):
        if isinstance(dashboard_key, dict):
            filters = dashboard_key
            dashboard_key = (filters or {}).get('dashboard') or 'executive'
        raw = dict(filters or {})
        raw['dashboard'] = dashboard_key
        methods = {
            'executive': self.get_executive_dashboard,
            'action_center': self.get_action_center_dashboard,
            'finance': self.get_finance_dashboard,
            'contracts': self.get_contracts_dashboard,
            'projects': self.get_projects_dashboard,
            'procurement': self.get_procurement_dashboard,
            'inventory': self.get_inventory_dashboard,
            'expenses': self.get_expenses_dashboard,
            'hr': self.get_hr_dashboard,
            'payroll': self.get_payroll_dashboard,
            'attendance': self.get_attendance_dashboard,
            'sales': self.get_sales_dashboard,
            'partners': self.get_partners_dashboard,
            'assets': self.get_assets_dashboard,
            'governance': self.get_governance_dashboard,
            'quality_data': self.get_data_quality_dashboard,
            'manufacturing': self.get_manufacturing_dashboard,
            'crm': self.get_crm_dashboard,
            'construction': self.get_construction_dashboard,
            'quality': self.get_quality_dashboard,
            'system': self.get_system_dashboard,
        }
        method = methods.get(dashboard_key) or self.get_executive_dashboard
        return method(raw)

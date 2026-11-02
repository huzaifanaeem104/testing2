# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesEnterpriseDashboardAssets(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_assets_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        has_oca = self._can_read('account.asset')
        has_om = self._can_read('account.asset.asset')
        if not has_oca and not has_om:
            return self._unavailable(scope, 'assets', 'No asset register is readable.')
        kpis = []
        charts = {}
        tables = {}
        warnings = ['OCA account.asset and OdooMates account.asset.asset are separate stacks and are not merged.']
        if has_oca:
            domain = self._scope_domain('account.asset', scope)
            count = self._search_count('account.asset', domain)
            purchase = self._read_group_sum('account.asset', domain, 'purchase_value') if self._has_field('account.asset', 'purchase_value') else 0.0
            residual = self._read_group_sum('account.asset', domain, 'value_residual') if self._has_field('account.asset', 'value_residual') else 0.0
            depreciated = self._read_group_sum('account.asset', domain, 'value_depreciated') if self._has_field('account.asset', 'value_depreciated') else 0.0
            salvage = self._read_group_sum('account.asset', domain, 'salvage_value') if self._has_field('account.asset', 'salvage_value') else 0.0
            kpis.extend([
                self._kpi(scope, 'oca_count', 'OCA assets', count, False, 'assets_oca', suffix='', basis='count'),
                self._kpi(scope, 'oca_purchase', 'OCA purchase value', purchase, False, 'assets_oca'),
                self._kpi(scope, 'oca_salvage', 'OCA salvage', salvage, False, 'assets_oca'),
                self._kpi(scope, 'oca_depreciated', 'OCA depreciated', depreciated, False, 'assets_oca'),
                self._kpi(scope, 'oca_residual', 'OCA residual', residual, False, 'assets_oca'),
            ])
            if self._has_field('account.asset', 'state'):
                charts['oca_states'] = self._group_chart('account.asset', domain, 'state', 'OCA asset state')
            if self._has_field('account.asset', 'profile_id'):
                charts['oca_category'] = self._group_chart('account.asset', domain, 'profile_id', 'OCA by profile')
            elif self._has_field('account.asset', 'category_id'):
                charts['oca_category'] = self._group_chart('account.asset', domain, 'category_id', 'OCA by category')
            if self._has_field('account.asset', 'current_project_id'):
                charts['oca_project'] = self._group_chart('account.asset', domain, 'current_project_id', 'OCA by project')
            if self._has_field('account.asset', 'current_location_id'):
                charts['oca_location'] = self._group_chart('account.asset', domain, 'current_location_id', 'OCA by location')
            missing = []
            if self._has_field('account.asset', 'current_project_id'):
                missing.extend(self._document_rows(
                    'account.asset', domain + [('current_project_id', '=', False)],
                    {'name': 'name', 'state': 'state'}, 'assets_oca', scope=scope,
                ))
            tables['oca'] = self._mgmt_table('OCA assets missing project', [
                {'key': 'name', 'label': 'Asset'}, {'key': 'state', 'label': 'State'},
            ], missing, 'assets_oca')
            if self._has_field('account.asset', 'current_location_id'):
                tables['oca_location'] = self._mgmt_table('OCA assets missing location', [
                    {'key': 'name', 'label': 'Asset'}, {'key': 'state', 'label': 'State'},
                ], self._document_rows(
                    'account.asset', domain + [('current_location_id', '=', False)],
                    {'name': 'name', 'state': 'state'}, 'assets_oca', scope=scope,
                ), 'assets_oca')
            cat_field = 'profile_id' if self._has_field('account.asset', 'profile_id') else ('category_id' if self._has_field('account.asset', 'category_id') else False)
            if cat_field:
                tables['oca_category'] = self._mgmt_table('OCA assets missing category/profile', [
                    {'key': 'name', 'label': 'Asset'}, {'key': 'state', 'label': 'State'},
                ], self._document_rows(
                    'account.asset', domain + [(cat_field, '=', False)],
                    {'name': 'name', 'state': 'state'}, 'assets_oca', scope=scope,
                ), 'assets_oca')
            tables['oca_draft'] = self._mgmt_table('OCA draft assets', [
                {'key': 'name', 'label': 'Asset'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'account.asset', domain + [('state', '=', 'draft')] if self._has_field('account.asset', 'state') else [('id', '=', 0)],
                {'name': 'name', 'state': 'state'}, 'assets_oca', scope=scope,
            ), 'assets_oca')
            if self._can_read('account.asset.line'):
                line_domain = self._scope_domain('account.asset.line', scope) + [
                    ('type', '=', 'depreciate'),
                ]
                posted_domain = (
                    line_domain + [('move_check', '=', True)]
                    + self._date_domain('line_date', scope['date_from'], scope['date_to'])
                )
                depreciation = self._read_group_sum('account.asset.line', posted_domain, 'amount')
                kpis.append(self._kpi(
                    scope, 'oca_period_depreciation', 'OCA posted depreciation',
                    depreciation, False, 'asset_lines_oca',
                    'Posted OCA depreciation lines in the selected line_date period.',
                    date_field='account.asset.line.line_date',
                ))
                trend = self._monthly_model_sum(
                    'account.asset.line', scope,
                    [('type', '=', 'depreciate'), ('move_check', '=', True)],
                    'line_date', 'amount',
                )
                charts['oca_depreciation'] = self._chart(
                    'bar', 'OCA posted depreciation trend', trend[0],
                    [{'label': 'Depreciation', 'data': trend[1]}],
                )
                tables['oca_overdue'] = self._mgmt_table('OCA overdue unposted depreciation', [
                    {'key': 'name', 'label': 'Line'},
                    {'key': 'asset', 'label': 'Asset'},
                    {'key': 'date', 'label': 'Date'},
                    {'key': 'amount', 'label': 'Amount'},
                ], self._document_rows(
                    'account.asset.line',
                    line_domain + [
                        ('move_check', '=', False),
                        ('line_date', '<', fields.Date.context_today(self)),
                    ],
                    {'name': 'name', 'asset': 'asset_id', 'date': 'line_date', 'amount': 'amount'},
                    'asset_lines_oca_all', order='line_date',
                    money_fields=('amount',), date_fields=('line_date',), scope=scope,
                ), 'asset_lines_oca_all')
        if has_om:
            domain = self._scope_domain('account.asset.asset', scope)
            count = self._search_count('account.asset.asset', domain)
            value = self._read_group_sum('account.asset.asset', domain, 'value') if self._has_field('account.asset.asset', 'value') else 0.0
            salvage = self._read_group_sum('account.asset.asset', domain, 'salvage_value') if self._has_field('account.asset.asset', 'salvage_value') else 0.0
            depreciated = 0.0
            if self._can_read('account.asset.depreciation.line'):
                depreciated = self._read_group_sum(
                    'account.asset.depreciation.line',
                    self._scope_domain('account.asset.depreciation.line', scope) + [('move_check', '=', True)],
                    'amount',
                )
            residual = (value or 0.0) - (salvage or 0.0) - (depreciated or 0.0)
            kpis.extend([
                self._kpi(scope, 'om_count', 'OdooMates assets', count, False, 'assets_om', suffix='', basis='count'),
                self._kpi(scope, 'om_value', 'OdooMates value', value, False, 'assets_om'),
                self._kpi(scope, 'om_salvage', 'OdooMates salvage', salvage, False, 'assets_om'),
                self._kpi(scope, 'om_depreciated', 'OdooMates posted depreciation', depreciated, False, 'asset_lines_om'),
                self._kpi(scope, 'om_residual', 'OdooMates residual', residual, False, 'assets_om'),
            ])
            if self._has_field('account.asset.asset', 'state'):
                charts['om_states'] = self._group_chart('account.asset.asset', domain, 'state', 'OdooMates asset state')
            if self._has_field('account.asset.asset', 'category_id'):
                charts['om_category'] = self._group_chart('account.asset.asset', domain, 'category_id', 'OdooMates by category')
                tables['om_missing_category'] = self._mgmt_table('OdooMates assets missing category', [
                    {'key': 'name', 'label': 'Asset'}, {'key': 'state', 'label': 'State'},
                ], self._document_rows(
                    'account.asset.asset', domain + [('category_id', '=', False)],
                    {'name': 'name', 'state': 'state'}, 'assets_om', scope=scope,
                ), 'assets_om')
            tables['om_draft'] = self._mgmt_table('OdooMates draft assets', [
                {'key': 'name', 'label': 'Asset'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'account.asset.asset',
                domain + [('state', '=', 'draft')] if self._has_field('account.asset.asset', 'state') else [('id', '=', 0)],
                {'name': 'name', 'state': 'state'}, 'assets_om', scope=scope,
            ), 'assets_om')
            if self._can_read('account.asset.depreciation.line'):
                trend = self._monthly_model_sum(
                    'account.asset.depreciation.line', scope,
                    [('move_check', '=', True)], 'depreciation_date', 'amount',
                )
                charts['om_depreciation'] = self._chart(
                    'bar', 'OdooMates posted depreciation trend', trend[0],
                    [{'label': 'Depreciation', 'data': trend[1]}],
                )
                tables['om_overdue'] = self._mgmt_table('OdooMates overdue unposted depreciation', [
                    {'key': 'name', 'label': 'Line'},
                    {'key': 'asset', 'label': 'Asset'},
                    {'key': 'date', 'label': 'Date'},
                    {'key': 'amount', 'label': 'Amount'},
                ], self._document_rows(
                    'account.asset.depreciation.line',
                    self._scope_domain('account.asset.depreciation.line', scope) + [
                        ('move_check', '=', False),
                        ('depreciation_date', '<', fields.Date.context_today(self)),
                    ],
                    {'name': 'name', 'asset': 'asset_id', 'date': 'depreciation_date', 'amount': 'amount'},
                    'asset_lines_om_all', order='depreciation_date',
                    money_fields=('amount',), date_fields=('depreciation_date',), scope=scope,
                ), 'asset_lines_om_all')
        transfers = 0
        if self._can_read('asset.transfer'):
            transfers = self._search_count('asset.transfer', self._scope_domain('asset.transfer', scope) + [('state', 'not in', ('done', 'cancelled'))])
            kpis.append(self._kpi(scope, 'transfers', 'Open asset transfers', transfers, False, 'asset_transfers', suffix='', basis='count'))
            if self._has_field('asset.transfer', 'state'):
                charts['transfers'] = self._group_chart('asset.transfer', self._scope_domain('asset.transfer', scope), 'state', 'Transfers by status')
        return self._payload(
            scope, 'assets', kpis, charts, tables, warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=[kpi.get('key') for kpi in kpis[:6] if kpi.get('key')],
                charts=list(charts.keys())[:4],
                tables=list(tables.keys())[:3],
            )},
        )

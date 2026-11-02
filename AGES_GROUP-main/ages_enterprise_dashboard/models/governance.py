# -*- coding: utf-8 -*-

from odoo import models


class AgesEnterpriseDashboardGovernance(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_governance_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        kpis = []
        charts = {}
        tables = {}
        pending_reviews = 0
        if self._can_read('tier.review') and self._has_field('tier.review', 'status'):
            pending_reviews = self._search_count('tier.review', [('status', 'in', ('waiting', 'pending'))])
            kpis.append(self._kpi(scope, 'reviews', 'Pending tier reviews', pending_reviews, False, 'tier_reviews', suffix='', basis='count'))
            charts['reviews'] = self._group_chart(
                'tier.review', [('status', 'in', ('waiting', 'pending'))], 'model', 'Pending reviews by model', 'bar',
            )
            oldest = self._search_read(
                'tier.review', [('status', 'in', ('waiting', 'pending'))],
                ['model', 'requested_by', 'status', 'create_date'] if self._has_field('tier.review', 'requested_by') else ['model', 'status', 'create_date'],
                limit=15, order='create_date',
            )
            tables['oldest'] = self._mgmt_table('Oldest pending reviews', [
                {'key': 'model', 'label': 'Model'}, {'key': 'status', 'label': 'Status'}, {'key': 'date', 'label': 'Requested'},
            ], [{
                'model': rec.get('model') or '',
                'status': rec.get('status') or '',
                'date': rec.get('create_date') or '',
                'res_id': rec.get('id'),
                'action_key': 'tier_reviews',
            } for rec in oldest], 'tier_reviews')
            if self._has_field('tier.review', 'status'):
                review_date = 'reviewed_date' if self._has_field('tier.review', 'reviewed_date') else 'create_date'
                approved_labels, approved_data = self._monthly_model_count(
                    'tier.review', scope, [('status', '=', 'approved')], review_date,
                )
                _labels, rejected_data = self._monthly_model_count(
                    'tier.review', scope, [('status', '=', 'rejected')], review_date,
                )
                charts['review_trend'] = self._chart('bar', 'Approved vs rejected reviews', approved_labels, [
                    {'label': 'Approved', 'data': approved_data},
                    {'label': 'Rejected', 'data': rejected_data},
                ])
        pending_pay = pending_pay_value = 0
        if self._has_field('account.payment', 'validation_status'):
            pending_domain = self._scope_domain('account.payment', scope, [('validation_status', 'in', ('waiting', 'pending'))])
            pending_pay = self._search_count('account.payment', pending_domain)
            amount_field = 'amount_company_currency_signed' if self._has_field('account.payment', 'amount_company_currency_signed') else 'amount'
            pending_pay_value = abs(self._read_group_sum('account.payment', pending_domain, amount_field) or 0.0)
            kpis.append(self._kpi(scope, 'payments', 'Payments pending approval', pending_pay, False, 'pending_payments', suffix='', basis='count'))
            kpis.append(self._kpi(scope, 'payment_amount', 'Pending payment amount', pending_pay_value, False, 'pending_payments'))
        pending_pr = pending_pr_value = 0
        if self._has_field('purchase.request', 'validation_status'):
            pr_domain = self._scope_domain('purchase.request', scope, [('validation_status', 'in', ('waiting', 'pending'))])
            pending_pr = self._search_count('purchase.request', pr_domain)
            if self._has_field('purchase.request', 'estimated_cost'):
                pending_pr_value = self._read_group_sum('purchase.request', pr_domain, 'estimated_cost')
            kpis.append(self._kpi(scope, 'pr', 'PR pending approval', pending_pr, False, 'pending_pr', suffix='', basis='count'))
            kpis.append(self._kpi(scope, 'pr_amount', 'Pending PR amount', pending_pr_value, False, 'pending_pr'))
        je_validate = 0
        if self._has_field('account.move', 'je_stage'):
            je_validate = self._search_count(
                'account.move',
                self._scope_domain('account.move', scope, [('je_stage', '=', 'validate')]),
            )
            kpis.append(self._kpi(scope, 'je', 'JE awaiting validation', je_validate, False, 'je_validate', suffix='', basis='count'))
        caps = self._capability_map()
        if caps.get('audit'):
            audit_domain = self._typed_date_domain('ages.deletion.audit', 'create_date', scope.get('date_from'), scope.get('date_to'))
            deleted = self._search_count('ages.deletion.audit', audit_domain)
            kpis.append(self._kpi(scope, 'deleted', 'Audited deletions', deleted, False, 'deletion_audit', suffix='', basis='count'))
            if self._has_field('ages.deletion.audit', 'model'):
                charts['audit'] = self._group_chart('ages.deletion.audit', audit_domain, 'model', 'Deletions by model', 'bar')
            if self._has_field('ages.deletion.audit', 'user_id'):
                charts['audit_user'] = self._group_chart('ages.deletion.audit', audit_domain, 'user_id', 'Deletions by user', 'bar')
        else:
            kpis.append(self._unavailable_kpi(scope, 'deleted', 'Deletion audit', 'ages.deletion.audit is not installed or not authorized.'))
        if caps.get('presence'):
            logged_in = self._search_count('ages.user.session', [('is_logged_in', '=', True)]) if self._has_field('ages.user.session', 'is_logged_in') else 0
            kpis.append(self._kpi(scope, 'sessions', 'Logged-in sessions', logged_in, False, 'user_sessions', suffix='', basis='count'))
        else:
            kpis.append(self._unavailable_kpi(scope, 'sessions', 'Logged-in users', 'Presence module is not installed or not authorized. IP/device details are never shown here.'))
        if caps.get('presence') and self._field_is_stored('ages.user.session', 'logout_reason'):
            timeouts = self._search_count('ages.user.session', [('logout_reason', '=', 'inactivity_timeout')])
            kpis.append(self._kpi(
                scope, 'timeouts', 'Inactivity timeouts', timeouts, False, 'timeout_sessions',
                'Stored logout_reason=inactivity_timeout. Not an invented approval SLA.', suffix='', basis='count',
            ))
        else:
            kpis.append(self._unavailable_kpi(
                scope, 'timeouts', 'Approval / session timeouts',
                'No stored approval-timeout model is readable. Inactivity timeouts appear when ages.user.session.logout_reason is stored and authorized. Oldest pending reviews are listed instead of invented SLA breaches.',
            ))
        if not kpis:
            return self._unavailable(scope, 'governance', 'No approval models are readable.')
        warnings = ['Audit snapshots, IP/device details, and session payloads are not exposed on this dashboard.']
        return self._payload(
            scope, 'governance', kpis, charts, tables, warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=[kpi.get('key') for kpi in kpis[:5] if kpi.get('key')],
                charts=list(charts.keys())[:3],
                tables=list(tables.keys())[:3],
            )},
        )

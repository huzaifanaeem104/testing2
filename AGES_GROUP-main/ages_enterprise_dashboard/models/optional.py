# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesEnterpriseDashboardOptional(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_manufacturing_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._can_read('mrp.production'):
            return self._unavailable(scope, 'manufacturing', 'Manufacturing is not installed or not readable.')
        date_from, date_to = scope['date_from'], scope['date_to']
        domain = self._scope_domain('mrp.production', scope)
        date_field = self._first_date_field('mrp.production', ('date_start', 'date_planned_start', 'date_deadline'))
        if date_field:
            domain += self._typed_date_domain('mrp.production', date_field, date_from, date_to)
        total = self._search_count('mrp.production', domain)
        done = self._search_count('mrp.production', domain + [('state', '=', 'done')])
        delayed = 0
        if self._has_field('mrp.production', 'date_deadline'):
            delayed = self._search_count('mrp.production', domain + [
                ('date_deadline', '<', fields.Date.context_today(self)),
                ('state', 'not in', ('done', 'cancel')),
            ])
        waiting_components = 0
        if self._has_field('mrp.production', 'reservation_state'):
            waiting_components = self._search_count('mrp.production', domain + [
                ('state', 'not in', ('done', 'cancel')),
                ('reservation_state', 'in', ('waiting', 'confirmed')),
            ])
        qty_planned = qty_done = 0.0
        if self._has_field('mrp.production', 'product_qty'):
            qty_planned = self._read_group_sum('mrp.production', domain, 'product_qty')
        produced_field = False
        for candidate in ('qty_produced', 'qty_producing'):
            if self._field_is_stored('mrp.production', candidate):
                produced_field = candidate
                break
        if produced_field:
            qty_done = self._read_group_sum('mrp.production', domain + [('state', '=', 'done')], produced_field)
        duration_hours = False
        if self._has_field('mrp.production', 'date_start') and self._has_field('mrp.production', 'date_finished'):
            mos = self.env['mrp.production'].search_fetch(
                domain + [('state', '=', 'done'), ('date_start', '!=', False), ('date_finished', '!=', False)],
                ['date_start', 'date_finished'],
                limit=200,
            )
            hours = [self._elapsed_hours(mo.date_start, mo.date_finished) for mo in mos]
            hours = [item for item in hours if item not in (None, False)]
            if hours:
                duration_hours = round(sum(hours) / float(len(hours)), 1)
        kpis = [
            self._kpi(scope, 'mo', 'Manufacturing orders', total, False, 'mrp_orders', suffix='', basis='count'),
            self._kpi(scope, 'done', 'Done', done, False, 'mrp_orders', suffix='', basis='count'),
            self._kpi(scope, 'delayed', 'Delayed open MOs', delayed, False, 'mrp_orders', suffix='', basis='count'),
            self._kpi(scope, 'waiting_comp', 'Open MOs waiting components', waiting_components, False, 'mrp_waiting',
                      'Open manufacturing orders whose stored reservation_state is waiting or confirmed.', suffix='', basis='count') if self._has_field('mrp.production', 'reservation_state') else self._unavailable_kpi(scope, 'waiting_comp', 'Component availability', 'mrp.production.reservation_state is not present.'),
            self._kpi(scope, 'planned_qty', 'Planned quantity', qty_planned, False, 'mrp_orders', suffix='', basis='count'),
            self._kpi(scope, 'done_qty', 'Produced quantity', qty_done, False, 'mrp_orders', suffix='', basis='count'),
            self._kpi(scope, 'duration', 'Avg completed MO hours', duration_hours or 0.0, False, 'mrp_orders',
                      'Average elapsed hours between stored date_start and date_finished on done MOs in this period (first 200).', suffix='', basis='count', kind='count') if duration_hours is not False else self._unavailable_kpi(scope, 'duration', 'Production duration', 'No completed MOs with stored start and finish datetimes in this period.'),
            self._unavailable_kpi(scope, 'mo_cost', 'Manufacturing cost', 'Cost is shown only when mrp_account stored actuals exist; they are not assumed here.'),
        ]
        charts = {
            'states': self._group_chart('mrp.production', domain, 'state', 'MO status'),
            'qty': self._chart('bar', 'Planned vs produced quantity', ['Planned', 'Produced'], [
                {'label': 'Quantity', 'data': [round(qty_planned or 0.0, 2), round(qty_done or 0.0, 2)]},
            ]),
        }
        if date_field:
            mo_trend = self._monthly_model_count('mrp.production', scope, [], date_field)
            charts['trend'] = self._chart(
                'bar', 'Manufacturing orders by month', mo_trend[0],
                [{'label': 'Orders', 'data': mo_trend[1]}],
            )
        if self._has_field('mrp.production', 'construction_project_id'):
            charts['construction'] = self._group_chart(
                'mrp.production', domain + [('construction_project_id', '!=', False)],
                'construction_project_id', 'MOs linked to construction projects', 'bar',
            )
        warnings = ['Current databases may have zero manufacturing orders; empty state is expected.']
        tables = {
            'delayed': self._mgmt_table('Delayed manufacturing orders', [
                {'key': 'name', 'label': 'MO'}, {'key': 'deadline', 'label': 'Deadline'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'mrp.production',
                domain + [('date_deadline', '<', fields.Date.context_today(self)), ('state', 'not in', ('done', 'cancel'))] if self._has_field('mrp.production', 'date_deadline') else [('id', '=', 0)],
                {'name': 'name', 'deadline': 'date_deadline', 'state': 'state'},
                'mrp_orders', order='date_deadline', date_fields=('date_deadline',), scope=scope,
            ), 'mrp_orders'),
        }
        if self._has_field('mrp.production', 'reservation_state'):
            tables['waiting'] = self._mgmt_table('Open MOs waiting components', [
                {'key': 'name', 'label': 'MO'}, {'key': 'state', 'label': 'State'}, {'key': 'reservation', 'label': 'Reservation'},
            ], self._document_rows(
                'mrp.production',
                domain + [('state', 'not in', ('done', 'cancel')), ('reservation_state', 'in', ('waiting', 'confirmed'))],
                {'name': 'name', 'state': 'state', 'reservation': 'reservation_state'},
                'mrp_waiting', scope=scope,
            ), 'mrp_waiting')
        return self._payload(
            scope, 'manufacturing', kpis, charts, tables,
            date_field='mrp.production.%s' % (date_field or 'date_start'), warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['mo', 'done', 'delayed', 'waiting_comp', 'planned_qty', 'done_qty'],
                charts=[('states', 4), ('trend', 8), ('qty', 6)],
                tables=['delayed', 'waiting'],
            )},
        )

    def get_crm_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._can_read('crm.lead'):
            return self._unavailable(scope, 'crm', 'CRM is not installed.')
        date_from, date_to = scope['date_from'], scope['date_to']
        domain = self._scope_domain('crm.lead', scope)
        date_field = self._first_date_field('crm.lead', ('date_open', 'create_date'))
        if date_field:
            domain += self._typed_date_domain('crm.lead', date_field, date_from, date_to)
        leads = self._search_count('crm.lead', domain)
        won = 0
        if self._has_field('crm.lead', 'probability'):
            won = self.env['crm.lead'].with_context(active_test=False).search_count(
                domain + [('probability', '=', 100)]
            )
        lost = 0
        if self._has_field('crm.lead', 'active'):
            lost_domain = domain + [('active', '=', False)]
            if self._has_field('crm.lead', 'probability'):
                lost_domain += [('probability', '<', 100)]
            lost = self.env['crm.lead'].with_context(active_test=False).search_count(lost_domain)
        expected = self._read_group_sum('crm.lead', domain, 'expected_revenue') if self._has_field('crm.lead', 'expected_revenue') else 0.0
        weighted = False
        if self._has_field('crm.lead', 'prorated_revenue') and self._field_is_stored('crm.lead', 'prorated_revenue'):
            weighted = self._read_group_sum('crm.lead', domain, 'prorated_revenue')
        kpis = [
            self._kpi(scope, 'leads', 'Leads / opportunities', leads, False, 'crm_leads', suffix='', basis='count'),
            self._kpi(scope, 'won', 'Won (probability 100)', won, False, 'crm_leads', suffix='', basis='count'),
            self._kpi(scope, 'lost', 'Lost (archived, probability < 100)', lost, False, 'crm_leads',
                      'Archived leads with probability below 100 so won deals are not counted as lost.', suffix='', basis='count'),
            self._kpi(scope, 'expected', 'Expected revenue', expected, False, 'crm_leads'),
            self._kpi(scope, 'weighted', 'Stored prorated revenue', weighted or 0.0, False, 'crm_leads') if weighted is not False else self._unavailable_kpi(scope, 'weighted', 'Probability-weighted revenue', 'crm.lead.prorated_revenue is not stored, so it is not aggregated.'),
        ]
        charts = {}
        if self._has_field('crm.lead', 'stage_id'):
            charts['stages'] = self._group_chart('crm.lead', domain, 'stage_id', 'Pipeline by stage')
        if self._has_field('crm.lead', 'user_id'):
            charts['salespeople'] = self._group_chart('crm.lead', domain, 'user_id', 'Pipeline by salesperson', 'bar', value_field='expected_revenue' if self._has_field('crm.lead', 'expected_revenue') else False)
        if date_field:
            lead_trend = self._monthly_model_count('crm.lead', scope, [], date_field)
            charts['trend'] = self._chart(
                'bar', 'Leads by month', lead_trend[0],
                [{'label': 'Leads', 'data': lead_trend[1]}],
            )
        tables = {
            'leads': self._mgmt_table('Pipeline', [
                {'key': 'name', 'label': 'Lead'}, {'key': 'partner', 'label': 'Customer'}, {'key': 'expected', 'label': 'Expected'},
            ], self._document_rows(
                'crm.lead', domain,
                {'name': 'name', 'partner': 'partner_id', 'expected': 'expected_revenue'},
                'crm_leads', money_fields=('expected_revenue',), scope=scope,
            ), 'crm_leads'),
        }
        if self._has_field('crm.lead', 'activity_date_deadline'):
            tables['activities'] = self._mgmt_table('Leads with activity deadlines', [
                {'key': 'name', 'label': 'Lead'}, {'key': 'deadline', 'label': 'Activity deadline'},
            ], self._document_rows(
                'crm.lead', domain + [('activity_date_deadline', '!=', False)],
                {'name': 'name', 'deadline': 'activity_date_deadline'},
                'crm_leads', date_fields=('activity_date_deadline',), order='activity_date_deadline', scope=scope,
            ), 'crm_leads')
        return self._payload(
            scope, 'crm', kpis, charts, tables,
            date_field='crm.lead.%s' % (date_field or 'create_date'),
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['leads', 'won', 'lost', 'expected'],
                charts=[('stages', 4), ('trend', 8), ('salespeople', 12)],
                tables=['leads', 'activities'],
            )},
        )

    def get_construction_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._can_read('construction.boq'):
            return self._unavailable(scope, 'construction', 'Construction Pro is not installed. AGES contract/RA billing is a separate dashboard.')
        domain = self._scope_domain('construction.boq', scope)
        count = self._search_count('construction.boq', domain)
        kpis = [self._kpi(scope, 'boq', 'BOQ documents', count, False, 'construction_boq', suffix='', basis='count')]
        model_specs = (
            ('construction.change.order', 'co', 'Change orders', 'construction_co'),
            ('construction.material.request', 'mr', 'Material requests', 'construction_mr'),
            ('construction.daily.log', 'log', 'Daily logs', 'construction_log'),
            ('construction.progress.entry', 'progress', 'Progress entries', 'construction_progress'),
            ('construction.rfi', 'rfi', 'RFIs', 'construction_rfi'),
            ('construction.subcontract', 'sub', 'Subcontracts', 'construction_sub'),
            ('construction.equipment.assignment', 'eq', 'Equipment assignments', 'construction_eq'),
        )
        charts = {}
        tables = {
            'boq': self._mgmt_table('BOQ documents', [
                {'key': 'name', 'label': 'BOQ'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'construction.boq', domain,
                {'name': 'name', 'state': 'state'} if self._has_field('construction.boq', 'state') else {'name': 'name'},
                'construction_boq', scope=scope,
            ), 'construction_boq'),
        }
        if self._has_field('construction.boq', 'state'):
            charts['boq_state'] = self._group_chart('construction.boq', domain, 'state', 'BOQ status')
        for model_name, key, label, action in model_specs:
            if self._can_read(model_name):
                model_domain = self._scope_domain(model_name, scope)
                kpis.append(self._kpi(scope, key, label, self._search_count(model_name, model_domain), False, action, suffix='', basis='count'))
                if self._has_field(model_name, 'state') and key not in charts:
                    charts[key] = self._group_chart(model_name, model_domain, 'state', '%s by state' % label)
                tables[key] = self._mgmt_table(label, [
                    {'key': 'name', 'label': 'Record'}, {'key': 'state', 'label': 'State'},
                ], self._document_rows(
                    model_name, model_domain,
                    {'name': 'name', 'state': 'state'} if self._has_field(model_name, 'state') else {'name': 'name'},
                    action, scope=scope,
                ), action)
            else:
                kpis.append(self._unavailable_kpi(scope, key, label, '%s is not readable.' % model_name))
        warnings = [
            'Construction Pro is not wired to ages.contract / running bills. Do not double-count contract values.',
            'Non-stored construction project KPI fields are not aggregated.',
        ]
        return self._payload(
            scope, 'construction', kpis, charts, tables, warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=[kpi.get('key') for kpi in kpis[:6] if kpi.get('key')],
                charts=[('boq_state', 4)] + [(key, 4) for key in charts if key != 'boq_state'][:5],
                tables=['boq'],
            )},
        )

    def get_quality_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._can_read('quality.check'):
            return self._unavailable(scope, 'quality', 'Quality is not installed.')
        date_from, date_to = scope['date_from'], scope['date_to']
        domain = self._scope_domain('quality.check', scope)
        date_field = self._first_date_field('quality.check', ('control_date', 'date'))
        if date_field:
            domain += self._typed_date_domain('quality.check', date_field, date_from, date_to)
        total = self._search_count('quality.check', domain)
        failed = self._search_count('quality.check', domain + [('quality_state', '=', 'fail')]) if self._has_field('quality.check', 'quality_state') else 0
        passed = self._search_count('quality.check', domain + [('quality_state', '=', 'pass')]) if self._has_field('quality.check', 'quality_state') else 0
        pending = max(total - failed - passed, 0)
        kpis = [
            self._kpi(scope, 'checks', 'Quality checks', total, False, 'quality_checks', suffix='', basis='count'),
            self._kpi(scope, 'pass', 'Passed', passed, False, 'quality_checks', suffix='', basis='count'),
            self._kpi(scope, 'fail', 'Failed', failed, False, 'quality_failed', suffix='', basis='count'),
            self._kpi(scope, 'pending', 'Pending', pending, False, 'quality_pending', suffix='', basis='count'),
        ]
        charts = {}
        if self._has_field('quality.check', 'quality_state'):
            charts['states'] = self._group_chart('quality.check', domain, 'quality_state', 'Quality outcome')
        if self._has_field('quality.check', 'product_id'):
            charts['products'] = self._group_chart('quality.check', domain + [('quality_state', '=', 'fail')], 'product_id', 'Failed checks by product', 'bar')
        if self._has_field('quality.check', 'picking_id'):
            charts['pickings'] = self._group_chart('quality.check', domain, 'picking_id', 'Checks by picking', 'bar')
        if date_field:
            q_trend = self._monthly_model_count('quality.check', scope, [], date_field)
            charts['trend'] = self._chart(
                'bar', 'Quality checks by month', q_trend[0],
                [{'label': 'Checks', 'data': q_trend[1]}],
            )
        tables = {
            'failed': self._mgmt_table('Failed checks awaiting resolution', [
                {'key': 'name', 'label': 'Check'}, {'key': 'product', 'label': 'Product'},
            ], self._document_rows(
                'quality.check', domain + [('quality_state', '=', 'fail')] if self._has_field('quality.check', 'quality_state') else [('id', '=', 0)],
                {'name': 'name', 'product': 'product_id'},
                'quality_failed', scope=scope,
            ), 'quality_failed'),
        }
        return self._payload(
            scope, 'quality', kpis, charts, tables,
            date_field='quality.check.%s' % (date_field or 'create_date'),
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['checks', 'pass', 'fail', 'pending'],
                charts=[('states', 4), ('trend', 8), ('products', 12)],
                tables=['failed'],
            )},
        )

    def get_system_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        caps = self._capability_map()
        if not caps.get('presence') and not caps.get('audit'):
            return self._unavailable(scope, 'system', 'Presence/audit modules are not installed or not authorized.')
        date_from, date_to = scope['date_from'], scope['date_to']
        kpis = []
        charts = {}
        tables = {}
        if caps.get('presence'):
            logged_in = self._search_count('ages.user.session', [('is_logged_in', '=', True)]) if self._has_field('ages.user.session', 'is_logged_in') else 0
            kpis.append(self._kpi(scope, 'sessions', 'Logged-in sessions', logged_in, False, 'user_sessions', suffix='', basis='count'))
            if self._has_field('ages.user.session', 'state'):
                charts['session_state'] = self._group_chart('ages.user.session', [], 'state', 'Session state')
            if self._field_is_stored('ages.user.session', 'logout_reason'):
                timeout_domain = [('logout_reason', '=', 'inactivity_timeout')]
                timeout_domain += self._typed_date_domain('ages.user.session', 'write_date', date_from, date_to)
                timeouts = self._search_count('ages.user.session', timeout_domain)
                kpis.append(self._kpi(
                    scope, 'timeouts', 'Inactivity timeouts', timeouts, False, 'timeout_sessions',
                    'Stored logout_reason=inactivity_timeout on ages.user.session.', suffix='', basis='count',
                ))
            else:
                kpis.append(self._unavailable_kpi(
                    scope, 'timeouts', 'Inactivity timeouts',
                    'logout_reason is not a stored field on ages.user.session.',
                ))
        if caps.get('audit'):
            audit_domain = self._typed_date_domain('ages.deletion.audit', 'create_date', date_from, date_to)
            deleted = self._search_count('ages.deletion.audit', audit_domain)
            kpis.append(self._kpi(scope, 'deleted', 'Audited deletions', deleted, False, 'deletion_audit', suffix='', basis='count'))
            if self._has_field('ages.deletion.audit', 'model'):
                charts['audit'] = self._group_chart('ages.deletion.audit', audit_domain, 'model', 'Deletions by model', 'bar')
            if self._has_field('ages.deletion.audit', 'user_id'):
                charts['audit_user'] = self._group_chart('ages.deletion.audit', audit_domain, 'user_id', 'Deletions by user', 'bar')
            tables['audit'] = self._mgmt_table('Recent deletions', [
                {'key': 'name', 'label': 'Record'}, {'key': 'model', 'label': 'Model'},
            ], self._document_rows(
                'ages.deletion.audit', audit_domain,
                {'name': 'name', 'model': 'model'} if self._has_field('ages.deletion.audit', 'name') else {'model': 'model'},
                'deletion_audit', order='create_date desc', scope=scope,
            ), 'deletion_audit')
        warnings = ['Session IP/device details are not displayed.']
        return self._payload(
            scope, 'system', kpis, charts, tables, warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=[kpi.get('key') for kpi in kpis[:4] if kpi.get('key')],
                charts=list(charts.keys())[:3],
                tables=list(tables.keys())[:2],
            )},
        )

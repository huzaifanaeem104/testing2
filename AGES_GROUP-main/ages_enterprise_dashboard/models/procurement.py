# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesEnterpriseDashboardProcurement(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_procurement_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        caps = self._capability_map()
        if not caps.get('purchase') and not caps.get('purchase_request'):
            return self._unavailable(scope, 'procurement', 'Purchase or purchase-request access is required.')
        date_from, date_to = scope['date_from'], scope['date_to']
        po_domain = self._scope_domain('purchase.order', scope) if self._can_read('purchase.order') else []
        rfq = confirmed = cancelled = 0
        po_value = open_value = billed_value = rfq_value = 0.0
        if self._can_read('purchase.order'):
            period_po = po_domain + self._date_domain('date_order', date_from, date_to)
            rfq = self._search_count('purchase.order', period_po + [('state', 'in', ('draft', 'sent', 'to approve'))])
            rfq_value = self._currency_sum(
                'purchase.order',
                period_po + [('state', 'in', ('draft', 'sent', 'to approve'))],
                'amount_untaxed', scope, date_field='date_order',
            )
            confirmed = self._search_count('purchase.order', period_po + [('state', 'in', ('purchase', 'done'))])
            cancelled = self._search_count('purchase.order', period_po + [('state', '=', 'cancel')])
        period_line_values = self._po_line_values(scope, date_from, date_to)
        open_line_values = self._po_line_values(scope, False, False)
        po_value = period_line_values['ordered']
        billed_value = period_line_values['billed']
        unbilled_value = max(po_value - billed_value, 0.0)
        open_value = max(open_line_values['ordered'] - open_line_values['billed'], 0.0)
        unreceived_value = max(
            open_line_values['ordered'] - open_line_values['received'], 0.0
        )
        qty_ordered = qty_received = qty_invoiced = 0.0
        if self._can_read('purchase.order.line'):
            line_domain = self._scope_domain('purchase.order.line', scope, [
                ('order_id.state', 'in', ('purchase', 'done')),
            ]) + self._date_domain('date_order', date_from, date_to)
            qty_ordered = self._read_group_sum('purchase.order.line', line_domain, 'product_qty')
            if self._has_field('purchase.order.line', 'qty_received'):
                qty_received = self._read_group_sum('purchase.order.line', line_domain, 'qty_received')
            if self._has_field('purchase.order.line', 'qty_invoiced'):
                qty_invoiced = self._read_group_sum('purchase.order.line', line_domain, 'qty_invoiced')
        pending_receipt_qty = max((qty_ordered or 0.0) - (qty_received or 0.0), 0.0)
        unbilled_qty = max((qty_ordered or 0.0) - (qty_invoiced or 0.0), 0.0)

        pr_total = pr_pending = pr_approved = pr_progress = pr_done = pr_rejected = 0
        pr_value = pr_pending_value = 0.0
        qty_requested = qty_in_progress = qty_done = qty_cancelled = pending_qty = 0.0
        if self._can_read('purchase.request'):
            pr_domain = self._scope_domain('purchase.request', scope)
            period_pr = pr_domain + self._date_domain('date_start', date_from, date_to)
            pr_total = self._search_count('purchase.request', period_pr)
            if self._has_field('purchase.request', 'validation_status'):
                pr_pending = self._search_count('purchase.request', pr_domain + [('validation_status', 'in', ('waiting', 'pending'))])
                pr_pending_value = self._currency_sum(
                    'purchase.request',
                    pr_domain + [('validation_status', 'in', ('waiting', 'pending'))],
                    'estimated_cost',
                    scope, date_field='date_start', company_currency=True,
                ) if self._has_field('purchase.request', 'estimated_cost') else 0.0
            for state, target in (('approved', 'approved'), ('in_progress', 'progress'), ('done', 'done'), ('rejected', 'rejected'), ('to_approve', 'to_approve')):
                count = self._search_count('purchase.request', period_pr + [('state', '=', state)])
                if state == 'approved':
                    pr_approved = count
                elif state == 'in_progress':
                    pr_progress = count
                elif state == 'done':
                    pr_done = count
                elif state == 'rejected':
                    pr_rejected = count
            if self._has_field('purchase.request', 'estimated_cost'):
                pr_value = self._currency_sum(
                    'purchase.request', period_pr, 'estimated_cost', scope,
                    date_field='date_start', company_currency=True,
                )
        if self._can_read('purchase.request.line'):
            prl_domain = self._scope_domain('purchase.request.line', scope)
            prl_domain += self._date_domain('date_start', date_from, date_to)
            qty_requested = self._read_group_sum('purchase.request.line', prl_domain, 'product_qty')
            if self._has_field('purchase.request.line', 'qty_in_progress'):
                qty_in_progress = self._read_group_sum('purchase.request.line', prl_domain, 'qty_in_progress')
            if self._has_field('purchase.request.line', 'qty_done'):
                qty_done = self._read_group_sum('purchase.request.line', prl_domain, 'qty_done')
            if self._has_field('purchase.request.line', 'qty_cancelled'):
                qty_cancelled = self._read_group_sum('purchase.request.line', prl_domain, 'qty_cancelled')
            if self._has_field('purchase.request.line', 'pending_qty_to_receive'):
                pending_qty = self._read_group_sum('purchase.request.line', prl_domain, 'pending_qty_to_receive')

        today = fields.Date.context_today(self)
        overdue_receipts = 0
        if self._can_read('stock.picking'):
            overdue_receipts = self._search_count('stock.picking', self._scope_domain('stock.picking', scope, [
                ('picking_type_code', '=', 'incoming'),
                ('state', 'not in', ('done', 'cancel')),
                ('scheduled_date', '<', today),
            ]))
        vendor_bills = 0.0
        if self._can_read('account.move'):
            vendor_bills = abs(self._currency_sum(
                'account.move',
                self._scope_domain('account.move', scope, [
                    ('move_type', 'in', ('in_invoice', 'in_refund')),
                    ('state', '=', 'posted'),
                ]),
                'amount_residual_signed',
                scope, date_field='date', company_currency=True,
            ) or 0.0)
        approval_hours = (
            self._pr_average_approval_hours(scope)
            if self._can_read('tier.review') and self._has_field('tier.review', 'reviewed_date')
            else None
        )

        kpis = [
            self._kpi(scope, 'pr', 'Purchase requests', pr_total, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'pr_value', 'PR estimated cost', pr_value, False, 'purchase_requests'),
            self._kpi(scope, 'pr_pending', 'PR pending approval', pr_pending, False, 'pending_pr', suffix='', basis='count'),
            self._kpi(scope, 'pr_pending_value', 'Pending PR value', pr_pending_value, False, 'pending_pr'),
            self._kpi(scope, 'pr_approved', 'Approved PRs', pr_approved, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'pr_progress', 'In-progress PRs', pr_progress, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'pr_done', 'Done PRs', pr_done, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'pr_rejected', 'Rejected PRs', pr_rejected, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(
                scope, 'pr_avg_time', 'Average PR approval time',
                approval_hours, False, 'approved_pr',
                'Elapsed hours from purchase.request.create_date to the last approved '
                'tier.review.reviewed_date for validated PRs.',
                suffix=' h', basis='duration',
            ) if approval_hours is not None else self._unavailable_kpi(
                scope, 'pr_avg_time', 'Average PR approval time',
                'No validated PR has a complete approved tier.review timestamp in this scope.',
            ),
            self._kpi(scope, 'rfq', 'RFQs', rfq, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'rfq_value', 'RFQ value', rfq_value, False, 'purchase_orders'),
            self._kpi(scope, 'confirmed', 'Confirmed POs', confirmed, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'cancelled', 'Cancelled POs', cancelled, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'po_value', 'Confirmed PO value', po_value, False, 'purchase_orders'),
            self._kpi(scope, 'open', 'Open purchase commitment', open_value, False, 'purchase_orders',
                      'Confirmed PO line subtotal less proportional qty_invoiced value across all dates.'),
            self._kpi(scope, 'unreceived_value', 'PO value pending receipt', unreceived_value, False, 'purchase_orders',
                      'Confirmed PO line subtotal less proportional qty_received value.'),
            self._kpi(scope, 'billed_po', 'Billed PO value', billed_value, False, 'purchase_orders',
                      'PO line subtotal allocated by qty_invoiced / product_qty.'),
            self._kpi(scope, 'unbilled_value', 'Unbilled PO value', unbilled_value, False, 'purchase_orders',
                      'Period confirmed PO line value minus proportional billed value.'),
            self._kpi(scope, 'qty_requested', 'PR qty requested', qty_requested, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'qty_in_progress', 'PR qty in progress', qty_in_progress, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'qty_done', 'PR qty received/done', qty_done, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'qty_cancelled', 'PR qty cancelled', qty_cancelled, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'pending_qty', 'PR pending qty to receive', pending_qty, False, 'purchase_requests', suffix='', basis='count'),
            self._kpi(scope, 'ordered', 'PO qty ordered', qty_ordered, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'received', 'PO qty received', qty_received, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'invoiced', 'PO qty billed', qty_invoiced, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'pending_receipt_qty', 'PO qty pending receipt', pending_receipt_qty, False, 'overdue_receipts', suffix='', basis='count'),
            self._kpi(scope, 'unbilled_qty', 'PO qty not yet billed', unbilled_qty, False, 'purchase_orders', suffix='', basis='count'),
            self._kpi(scope, 'overdue_receipts', 'Overdue receipts', overdue_receipts, False, 'overdue_receipts', suffix='', basis='count'),
            self._kpi(scope, 'vendor_bills', 'Vendor bill outstanding', vendor_bills, False, 'vendor_bills'),
        ]
        vendor_rows = []
        project_rows = []
        product_rows = []
        requester_rows = []
        if self._can_read('purchase.order'):
            groups = self.env['purchase.order'].read_group(
                po_domain + self._date_domain('date_order', date_from, date_to) + [('state', 'in', ('purchase', 'done'))],
                ['amount_untaxed:sum'], ['partner_id'], lazy=False,
            )
            for group in sorted(groups, key=lambda item: item.get('amount_untaxed') or 0.0, reverse=True)[:10]:
                partner = group.get('partner_id')
                amount = group.get('amount_untaxed') or 0.0
                vendor_rows.append({
                    'name': partner[1] if partner else 'Unknown',
                    'formatted': self._format_money(amount, scope),
                    'amount': amount,
                    'res_id': partner[0] if partner else False,
                    'res_field': 'partner_id',
                    'action_key': 'purchase_orders',
                })
            project_path = self._project_path('purchase.order')
            if project_path:
                pgroups = self.env['purchase.order'].read_group(
                    po_domain + self._date_domain('date_order', date_from, date_to) + [('state', 'in', ('purchase', 'done'))],
                    ['amount_untaxed:sum'], [project_path], lazy=False,
                )
                for group in sorted(pgroups, key=lambda item: item.get('amount_untaxed') or 0.0, reverse=True)[:10]:
                    project = group.get(project_path)
                    amount = group.get('amount_untaxed') or 0.0
                    project_rows.append({
                        'name': project[1] if isinstance(project, (list, tuple)) and project else (project or 'Unassigned'),
                        'formatted': self._format_money(amount, scope),
                        'amount': amount,
                        'res_id': project[0] if isinstance(project, (list, tuple)) and project else False,
                        'res_field': project_path,
                        'action_key': 'purchase_orders',
                    })
        if self._can_read('purchase.order.line') and self._has_field('purchase.order.line', 'product_id'):
            lgroups = self.env['purchase.order.line'].read_group(
                self._scope_domain('purchase.order.line', scope, [
                    ('order_id.state', 'in', ('purchase', 'done')),
                ]) + self._date_domain('date_order', date_from, date_to),
                ['product_qty:sum'], ['product_id'], lazy=False,
            )
            for group in sorted(lgroups, key=lambda item: item.get('product_qty') or 0.0, reverse=True)[:10]:
                product = group.get('product_id')
                product_rows.append({
                    'name': product[1] if product else 'Unknown',
                    'qty': group.get('product_qty') or 0.0,
                    'res_id': product[0] if product else False,
                    'res_field': 'product_id',
                    'action_key': 'purchase_order_lines',
                })
        if self._can_read('purchase.request') and self._has_field('purchase.request', 'requested_by'):
            rgroups = self.env['purchase.request'].read_group(
                self._scope_domain('purchase.request', scope) + self._date_domain('date_start', date_from, date_to),
                ['estimated_cost:sum'] if self._has_field('purchase.request', 'estimated_cost') else ['id:count'],
                ['requested_by'], lazy=False,
            )
            for group in rgroups[:10]:
                user = group.get('requested_by')
                requester_rows.append({
                    'name': user[1] if user else 'Unassigned',
                    'formatted': self._format_money(group.get('estimated_cost') or 0.0, scope),
                    'amount': group.get('estimated_cost') or 0.0,
                    'res_id': user[0] if user else False,
                    'res_field': 'requested_by',
                    'action_key': 'purchase_requests',
                })
        monthly = self._po_monthly(scope)
        qty_month = self._purchase_qty_monthly(scope)
        charts = {
            'pr_funnel': self._group_chart(
                'purchase.request',
                self._scope_domain('purchase.request', scope) + self._date_domain('date_start', date_from, date_to),
                'state', 'PR status funnel', 'bar',
            ) if self._can_read('purchase.request') else self._chart('bar', 'PR status funnel', [], []),
            'po_states': self._group_chart(
                'purchase.order', po_domain + self._date_domain('date_order', date_from, date_to), 'state', 'PO status',
            ) if self._can_read('purchase.order') else self._chart('doughnut', 'PO status', [], []),
            'invoice_status': self._group_chart(
                'purchase.order', po_domain + [('state', 'in', ('purchase', 'done'))], 'invoice_status', 'PO invoice status',
            ) if self._can_read('purchase.order') and self._has_field('purchase.order', 'invoice_status') else self._chart('doughnut', 'PO invoice status', [], []),
            'qty': self._chart('bar', 'Requested vs ordered vs received', ['PR requested', 'PR done', 'PO ordered', 'PO received', 'PO billed'], [
                {'label': 'Quantity', 'data': [
                    round(qty_requested or 0.0, 2), round(qty_done or 0.0, 2),
                    round(qty_ordered or 0.0, 2), round(qty_received or 0.0, 2), round(qty_invoiced or 0.0, 2),
                ]},
            ]),
            'po_values': self._chart(
                'mixed', 'PO ordered / received / billed value',
                ['Ordered', 'Received', 'Billed'],
                [{'label': 'Value', 'data': [
                    round(period_line_values.get('ordered') or 0.0, 2),
                    round(period_line_values.get('received') or 0.0, 2),
                    round(period_line_values.get('billed') or 0.0, 2),
                ]}],
                unit='money', size='lg', allow_toggle=True, why_key='po_value',
            ),
            'monthly': self._chart(
                'area', 'Monthly confirmed PO value', monthly[0],
                [{'label': 'Untaxed', 'data': monthly[1]}],
                unit='money', allow_toggle=True,
            ),
            'qty_month': self._chart('bar', 'Ordered vs received vs billed by month', qty_month[0], [
                {'label': 'Ordered', 'data': qty_month[1]},
                {'label': 'Received', 'data': qty_month[2]},
                {'label': 'Billed', 'data': qty_month[3]},
            ]),
            'vendors': self._chart('horizontalBar', 'Purchases by vendor', [row['name'] for row in vendor_rows], [
                {'label': 'Untaxed', 'data': [round(row['amount'], 2) for row in vendor_rows]},
            ], unit='money', max_slices=9),
            'projects': self._chart('bar', 'Purchases by project', [row['name'] for row in project_rows], [
                {'label': 'Untaxed', 'data': [round(row['amount'], 2) for row in project_rows]},
            ]),
            'products': self._chart('bar', 'Purchases by product', [row['name'] for row in product_rows], [
                {'label': 'Qty', 'data': [round(row['qty'], 2) for row in product_rows]},
            ]),
            'requesters': self._chart('bar', 'PR by requester', [row['name'] for row in requester_rows], [
                {'label': 'Estimated', 'data': [round(row.get('amount') or 0.0, 2) for row in requester_rows]},
            ], action_key='purchase_requests', group_field='requested_by', label_ids=[row.get('res_id') for row in requester_rows]),
            'pr_age': self._pr_age_chart(scope),
        }
        pending_pr_rows = self._document_rows(
            'purchase.request',
            self._scope_domain('purchase.request', scope, [('validation_status', 'in', ('waiting', 'pending'))]) if self._has_field('purchase.request', 'validation_status') else [('id', '=', 0)],
            {'name': 'name', 'date': 'date_start', 'state': 'state', 'amount': 'estimated_cost'},
            'pending_pr', order='date_start', money_fields=('estimated_cost',), date_fields=('date_start',), scope=scope,
        ) if self._can_read('purchase.request') else []
        overdue_pick_rows = self._document_rows(
            'stock.picking',
            self._scope_domain('stock.picking', scope, [
                ('picking_type_code', '=', 'incoming'),
                ('state', 'not in', ('done', 'cancel')),
                ('scheduled_date', '<', today),
            ]),
            {'name': 'name', 'scheduled': 'scheduled_date', 'origin': 'origin', 'state': 'state'},
            'overdue_receipts', order='scheduled_date', date_fields=('scheduled_date',), scope=scope,
        ) if self._can_read('stock.picking') else []
        partial_pos = self._document_rows(
            'purchase.order',
            po_domain + [('state', 'in', ('purchase', 'done')), ('receipt_status', '=', 'partial')] if self._has_field('purchase.order', 'receipt_status') else [('id', '=', 0)],
            {'name': 'name', 'vendor': 'partner_id', 'amount': 'amount_untaxed'},
            'purchase_orders', money_fields=('amount_untaxed',), scope=scope,
        ) if self._can_read('purchase.order') else []
        unbilled_pos = self._document_rows(
            'purchase.order',
            po_domain + [('state', 'in', ('purchase', 'done')), ('invoice_status', 'in', ('no', 'to invoice'))],
            {'name': 'name', 'vendor': 'partner_id', 'amount': 'amount_untaxed'},
            'purchase_orders', money_fields=('amount_untaxed',), scope=scope,
        ) if self._can_read('purchase.order') else []
        delayed_pr_rows = []
        if self._can_read('purchase.request.line') and self._has_field('purchase.request.line', 'date_required'):
            delayed_domain = self._scope_domain('purchase.request.line', scope, [('date_required', '<', today)])
            if self._has_field('purchase.request.line', 'pending_qty_to_receive'):
                delayed_domain.append(('pending_qty_to_receive', '>', 0))
            delayed_pr_rows = self._document_rows(
                'purchase.request.line', delayed_domain,
                {'name': 'product_id', 'required': 'date_required', 'qty': 'product_qty'},
                'purchase_requests', order='date_required', date_fields=('date_required',), scope=scope,
            )
        tables = {
            'pending_pr': self._mgmt_table('Pending PR approvals', [
                {'key': 'name', 'label': 'PR'}, {'key': 'date', 'label': 'Date'}, {'key': 'state', 'label': 'State'}, {'key': 'amount', 'label': 'Estimated'},
            ], pending_pr_rows, 'pending_pr'),
            'delayed_pr': self._mgmt_table('Delayed PRs', [
                {'key': 'name', 'label': 'Line'}, {'key': 'required', 'label': 'Required'}, {'key': 'qty', 'label': 'Qty'},
            ], delayed_pr_rows, 'purchase_requests'),
            'overdue_receipts': self._mgmt_table('Overdue PO receipts', [
                {'key': 'name', 'label': 'Transfer'}, {'key': 'scheduled', 'label': 'Scheduled'}, {'key': 'origin', 'label': 'Source'}, {'key': 'state', 'label': 'State'},
            ], overdue_pick_rows, 'overdue_receipts'),
            'partial': self._mgmt_table('Partially received POs', [
                {'key': 'name', 'label': 'PO'}, {'key': 'vendor', 'label': 'Vendor'}, {'key': 'amount', 'label': 'Untaxed'},
            ], partial_pos, 'purchase_orders', empty='receipt_status is required; empty if that field is absent.'),
            'unbilled': self._mgmt_table('Ordered not billed POs', [
                {'key': 'name', 'label': 'PO'}, {'key': 'vendor', 'label': 'Vendor'}, {'key': 'amount', 'label': 'Untaxed'},
            ], unbilled_pos, 'purchase_orders'),
            'vendors': self._mgmt_table('Top vendors', [
                {'key': 'name', 'label': 'Vendor'}, {'key': 'formatted', 'label': 'Amount'},
            ], vendor_rows, 'purchase_orders'),
            'products': self._mgmt_table('Top products', [
                {'key': 'name', 'label': 'Product'}, {'key': 'qty', 'label': 'Qty ordered'},
            ], product_rows, 'purchase_orders'),
            'projects': self._mgmt_table('Project purchase commitments', [
                {'key': 'name', 'label': 'Project'}, {'key': 'formatted', 'label': 'Amount'},
            ], project_rows, 'purchase_orders'),
        }
        cycles = self._procurement_cycle_times(scope)
        if cycles.get('pr_approval'):
            kpis.append(self._kpi(
                scope, 'cycle_pr_approval', 'PR approval average hours',
                cycles['pr_approval']['average'], False, 'approved_pr',
                'Elapsed hours from purchase.request.create_date to last approved tier.review.reviewed_date. Median %s, longest %s, n=%s.'
                % (cycles['pr_approval']['median'], cycles['pr_approval']['longest'], cycles['pr_approval']['count']),
                suffix=' h', basis='duration',
            ))
        if cycles.get('pr_to_po'):
            kpis.append(self._kpi(
                scope, 'cycle_pr_po', 'PR to PO average hours',
                cycles['pr_to_po']['average'], False, 'purchase_orders',
                'Elapsed hours from purchase.request.create_date to linked purchase.order.date_order via purchase_lines. Median %s, n=%s.'
                % (cycles['pr_to_po']['median'], cycles['pr_to_po']['count']),
                suffix=' h', basis='duration',
            ))
        else:
            kpis.append(self._unavailable_kpi(
                scope, 'cycle_pr_po', 'PR to PO average hours',
                'No purchase.request.line.purchase_lines linked to a confirmed PO date_order in this scope.',
            ))
        if cycles.get('po_to_receipt'):
            kpis.append(self._kpi(
                scope, 'cycle_po_receipt', 'PO to receipt average hours',
                cycles['po_to_receipt']['average'], False, 'receipts_done',
                'Elapsed hours from purchase.order.date_order to done stock.move date (actual_date when present) via purchase_line_id. Median %s, n=%s.'
                % (cycles['po_to_receipt']['median'], cycles['po_to_receipt']['count']),
                suffix=' h', basis='duration',
            ))
        else:
            kpis.append(self._unavailable_kpi(
                scope, 'cycle_po_receipt', 'PO to receipt average hours',
                'stock.move.purchase_line_id is missing or no done receipt moves exist in this scope.',
            ))
        warnings = [
            'purchased_qty on PR lines is not used; pending/done quantities use stored allocation fields.',
        ]
        self._attach_sparklines(kpis, {'po_value': (charts.get('monthly'), 0, 'money')})
        return self._payload(
            scope, 'procurement', kpis, charts, tables,
            date_field='purchase.order.date_order', warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['pr_pending', 'pr_pending_value', 'confirmed', 'po_value', 'unreceived_value', 'overdue_receipts'],
                charts=[('po_values', 8), ('po_states', 4), ('monthly', 6), ('vendors', 6)],
                tables=['pending_pr', 'overdue_receipts', 'unbilled', 'delayed_pr'],
            )},
        )

    def _po_monthly(self, scope, months=6):
        from datetime import timedelta
        if not self._can_read('purchase.order'):
            return [], []
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
            domain = self._scope_domain('purchase.order', scope, [('state', 'in', ('purchase', 'done'))])
            domain += self._date_domain('date_order', month_start, month_end)
            values.append(round(self._read_group_sum('purchase.order', domain, 'amount_untaxed') or 0.0, 2))
        return labels, values

    def _pr_age_chart(self, scope):
        labels = ['0-7d', '8-14d', '15-30d', '30d+']
        data = [0, 0, 0, 0]
        if not self._can_read('purchase.request') or not self._has_field('purchase.request', 'validation_status'):
            return self._chart('bar', 'PR approval queue by age', labels, [{'label': 'PRs', 'data': data}])
        today = fields.Date.context_today(self)
        records = self._search_read(
            'purchase.request',
            self._scope_domain('purchase.request', scope, [('validation_status', 'in', ('waiting', 'pending'))]),
            ['date_start'], limit=500, order='date_start',
        )
        for rec in records:
            start = rec.get('date_start')
            if not start:
                continue
            days = (today - start).days
            if days <= 7:
                data[0] += 1
            elif days <= 14:
                data[1] += 1
            elif days <= 30:
                data[2] += 1
            else:
                data[3] += 1
        return self._chart('bar', 'PR approval queue by age', labels, [{'label': 'PRs', 'data': data}])

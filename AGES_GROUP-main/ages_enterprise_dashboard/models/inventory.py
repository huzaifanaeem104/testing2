# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesEnterpriseDashboardInventory(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_inventory_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._capability_map().get('stock'):
            return self._unavailable(scope, 'inventory', 'Inventory user or manager access is required.')
        date_from, date_to = scope['date_from'], scope['date_to']
        qty_on_hand = qty_reserved = 0.0
        if self._can_read('stock.quant'):
            qdomain = self._scope_domain('stock.quant', scope) + [('location_id.usage', '=', 'internal')]
            qty_on_hand = self._read_group_sum('stock.quant', qdomain, 'quantity')
            if self._has_field('stock.quant', 'reserved_quantity'):
                qty_reserved = self._read_group_sum('stock.quant', qdomain, 'reserved_quantity')
        qty_available = (qty_on_hand or 0.0) - (qty_reserved or 0.0)
        stock_value = 0.0
        if self._can_read('stock.valuation.layer'):
            stock_value = self._read_group_sum(
                'stock.valuation.layer', self._scope_domain('stock.valuation.layer', scope), 'value',
            )
        move_value = 0.0
        if self._can_read('stock.valuation.layer'):
            svl_domain = self._scope_domain('stock.valuation.layer', scope)
            svl_date_field = 'actual_date' if self._has_field('stock.valuation.layer', 'actual_date') else 'create_date'
            svl_domain += self._typed_date_domain(
                'stock.valuation.layer', svl_date_field, date_from, date_to
            )
            move_value = self._read_group_sum('stock.valuation.layer', svl_domain, 'value')
        else:
            svl_date_field = 'create_date'
        date_field = 'actual_date' if self._has_field('stock.picking', 'actual_date') else 'scheduled_date'
        incoming = outgoing = internal = pending_in = pending_out = overdue = 0
        if self._can_read('stock.picking'):
            picking_domain = self._scope_domain('stock.picking', scope)
            incoming = picking_domain_plus(self, picking_domain, [
                ('picking_type_code', '=', 'incoming'), ('state', '=', 'done'),
            ], date_field, date_from, date_to)
            outgoing = picking_domain_plus(self, picking_domain, [
                ('picking_type_code', '=', 'outgoing'), ('state', '=', 'done'),
            ], date_field, date_from, date_to)
            internal = picking_domain_plus(self, picking_domain, [
                ('picking_type_code', '=', 'internal'), ('state', '=', 'done'),
            ], date_field, date_from, date_to)
            pending_in = self._search_count('stock.picking', picking_domain + [
                ('picking_type_code', '=', 'incoming'), ('state', 'not in', ('done', 'cancel')),
            ])
            pending_out = self._search_count('stock.picking', picking_domain + [
                ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel')),
            ])
            today = fields.Date.context_today(self)
            overdue = self._search_count('stock.picking', picking_domain + [
                ('state', 'not in', ('done', 'cancel')),
                ('scheduled_date', '<', today),
            ])
        negative = 0
        if self._can_read('stock.quant'):
            negative = self._search_count('stock.quant', self._scope_domain('stock.quant', scope) + [
                ('quantity', '<', 0), ('location_id.usage', '=', 'internal'),
            ])
        gate_count = gate_wait = overdue_rgp = 0
        if self._can_read('ages.gate.pass'):
            gdomain = self._scope_domain('ages.gate.pass', scope) + self._date_domain('pass_date', date_from, date_to)
            gate_count = self._search_count('ages.gate.pass', gdomain)
            if self._has_field('ages.gate.pass', 'state'):
                waiting = ['draft']
                try:
                    selection = self.env['ages.gate.pass']._fields['state'].selection
                    if callable(selection):
                        selection = selection(self.env['ages.gate.pass'])
                    if 'waiting_security' in dict(selection or []):
                        waiting.append('waiting_security')
                except Exception:
                    pass
                gate_wait = self._search_count('ages.gate.pass', self._scope_domain('ages.gate.pass', scope, [('state', 'in', tuple(waiting))]))
            if self._has_field('ages.gate.pass', 'return_state'):
                overdue_rgp = self._search_count('ages.gate.pass', self._scope_domain('ages.gate.pass', scope, [('return_state', '=', 'overdue')]))
        consumption = qty_consumed = 0.0
        if self._can_read('ages.material.consumption'):
            cdomain = self._scope_domain('ages.material.consumption', scope, [('state', '=', 'done')]) + self._date_domain('date', date_from, date_to)
            consumption = self._read_group_sum('ages.material.consumption', cdomain, 'amount_total')
            if self._has_field('ages.material.consumption', 'qty_consumed_total'):
                qty_consumed = self._read_group_sum('ages.material.consumption', cdomain, 'qty_consumed_total')
        q_pass = q_fail = q_pending = 0
        if self._can_read('quality.check') and self._has_field('quality.check', 'quality_state'):
            qdomain = self._scope_domain('quality.check', scope)
            q_pass = self._search_count('quality.check', qdomain + [('quality_state', '=', 'pass')])
            q_fail = self._search_count('quality.check', qdomain + [('quality_state', '=', 'fail')])
            q_pending = self._search_count('quality.check', qdomain + [('quality_state', 'not in', ('pass', 'fail'))])
        reorder_data = self._below_reorder_data(scope)

        kpis = [
            self._kpi(scope, 'qty', 'On-hand quantity', qty_on_hand, False, 'stock_quants', suffix='', basis='snapshot'),
            self._kpi(scope, 'available', 'Available (on-hand − reserved)', qty_available, False, 'stock_quants',
                      'quantity minus reserved_quantity on internal locations. Both fields are stored.', suffix='', basis='snapshot'),
            self._kpi(scope, 'value', 'Inventory value', stock_value, False, 'stock_valuation',
                      'Accounting stock.valuation.layer value (snapshot).'),
            self._kpi(scope, 'move_value', 'SVL movement value', move_value, False, 'stock_valuation_movement',
                      'Valuation layers whose %s falls in the period. Not a replacement for AML stock accounts.' % svl_date_field,
                      date_field='stock.valuation.layer.%s' % svl_date_field),
            self._kpi(scope, 'incoming', 'Receipts', incoming, False, 'receipts_done', suffix='', basis='count'),
            self._kpi(scope, 'outgoing', 'Deliveries', outgoing, False, 'deliveries_done', suffix='', basis='count'),
            self._kpi(scope, 'internal', 'Internal transfers', internal, False, 'internal_done', suffix='', basis='count'),
            self._kpi(scope, 'pending_in', 'Pending receipts', pending_in, False, 'pending_receipts', suffix='', basis='count'),
            self._kpi(scope, 'pending_out', 'Pending deliveries', pending_out, False, 'pending_deliveries', suffix='', basis='count'),
            self._kpi(scope, 'overdue', 'Overdue transfers', overdue, False, 'overdue_transfers', suffix='', basis='count'),
            self._kpi(scope, 'negative', 'Negative stock', negative, False, 'negative_stock', suffix='', basis='count'),
            self._kpi(scope, 'below_reorder', 'Below-reorder products', reorder_data['count'], False, 'orderpoints',
                      'Compares standard orderpoint qty_on_hand with stored product_min_qty. qty_on_hand is batch-read, never read_group aggregated.',
                      suffix='', basis='count') if reorder_data['available'] else self._unavailable_kpi(
                          scope, 'below_reorder', 'Below-reorder products', reorder_data['reason']
                      ),
            self._unavailable_kpi(scope, 'slow', 'Dead/slow stock',
                                  'No stored inbound-age/FIFO age exists on quants. Slow-moving horizon is configured but not applied as invented aging.'),
            self._kpi(scope, 'gate', 'Gate passes', gate_count, False, 'gate_passes', suffix='', basis='count'),
            self._kpi(scope, 'gate_wait', 'Gate passes waiting', gate_wait, False, 'waiting_gate_passes', suffix='', basis='count'),
            self._kpi(scope, 'overdue_rgp', 'Overdue RGP returns', overdue_rgp, False, 'overdue_rgp', suffix='', basis='count'),
            self._kpi(scope, 'consumption', 'Material consumption value', consumption, False, 'material_consumption'),
            self._kpi(scope, 'qty_consumed', 'Material consumption qty', qty_consumed, False, 'material_consumption', suffix='', basis='count'),
            self._kpi(scope, 'q_pass', 'Quality pass', q_pass, False, 'quality_checks', suffix='', basis='count'),
            self._kpi(scope, 'q_fail', 'Quality fail', q_fail, False, 'quality_failed', suffix='', basis='count'),
            self._kpi(scope, 'q_pending', 'Quality pending', q_pending, False, 'quality_pending', suffix='', basis='count'),
        ]
        charts = {
            'moves': self._chart('bar', 'Transfers this period', ['Receipts', 'Deliveries', 'Internal'], [
                {'label': 'Count', 'data': [incoming, outgoing, internal]},
            ]),
            'trend': self._picking_trend_chart(scope, date_field),
        }
        if self._can_read('stock.quant') and self._field_path_exists('stock.quant', 'product_id.categ_id'):
            charts['category'] = self._group_chart(
                'stock.quant',
                self._scope_domain('stock.quant', scope) + [('location_id.usage', '=', 'internal')],
                'product_id.categ_id', 'On-hand qty by category', 'bar', value_field='quantity',
            )
        if self._can_read('stock.valuation.layer') and self._field_path_exists('stock.valuation.layer', 'product_id.categ_id'):
            charts['value_category'] = self._related_group_chart(
                'stock.valuation.layer',
                self._scope_domain('stock.valuation.layer', scope),
                'product_id.categ_id', 'Inventory value by category', 'horizontalBar', value_field='value',
            )
        if self._can_read('stock.quant') and self._field_path_exists('stock.quant', 'location_id.warehouse_id'):
            charts['warehouse'] = self._group_chart(
                'stock.quant',
                self._scope_domain('stock.quant', scope) + [('location_id.usage', '=', 'internal')],
                'location_id.warehouse_id', 'On-hand qty by warehouse', 'bar', value_field='quantity',
            )
        if self._can_read('ages.gate.pass'):
            charts['gate_state'] = self._group_chart(
                'ages.gate.pass', self._scope_domain('ages.gate.pass', scope), 'state', 'Gate-pass status',
            )
            if self._has_field('ages.gate.pass', 'gate_type'):
                charts['gate_type'] = self._group_chart(
                    'ages.gate.pass', self._scope_domain('ages.gate.pass', scope), 'gate_type', 'Gate-pass type',
                )
        if self._can_read('ages.material.consumption'):
            charts['consumption_project'] = self._group_chart(
                'ages.material.consumption',
                self._scope_domain('ages.material.consumption', scope, [('state', '=', 'done')]),
                'project_id', 'Material consumption by project', 'bar', value_field='amount_total',
            )
        if self._can_read('quality.check') and self._has_field('quality.check', 'quality_state'):
            charts['quality'] = self._group_chart(
                'quality.check', self._scope_domain('quality.check', scope), 'quality_state', 'Quality outcome',
            )
        if self._can_read('stock.move') and self._has_field('stock.move', 'product_id'):
            move_domain = self._scope_domain('stock.move', scope) + [('state', '=', 'done')]
            move_date = 'actual_date' if self._has_field('stock.move', 'actual_date') else 'date'
            if self._has_field('stock.move', move_date):
                move_domain += self._typed_date_domain('stock.move', move_date, date_from, date_to)
            groups = self.env['stock.move'].read_group(move_domain, ['product_uom_qty:sum'], ['product_id'], lazy=False)
            top = sorted(groups, key=lambda item: abs(item.get('product_uom_qty') or 0.0), reverse=True)[:8]
            charts['movers'] = self._chart('horizontalBar', 'Top moving products', [(g.get('product_id') or [False, 'Unknown'])[1] for g in top], [
                {'label': 'Qty', 'data': [round(g.get('product_uom_qty') or 0.0, 2) for g in top]},
            ], unit='qty', max_slices=9)
        if self._can_read('stock.valuation.layer') and self._field_path_exists('stock.valuation.layer', 'product_id.categ_id'):
            charts['svl_category'] = self._group_chart(
                'stock.valuation.layer',
                self._scope_domain('stock.valuation.layer', scope),
                'product_id.categ_id', 'Inventory value by category', 'bar', value_field='value',
            )
        svl_warning = self._svl_gl_warning(scope)
        tables = {
            'negative': self._negative_stock_table(scope),
            'overdue': self._mgmt_table('Overdue transfers', [
                {'key': 'name', 'label': 'Transfer'}, {'key': 'scheduled', 'label': 'Scheduled'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'stock.picking',
                self._scope_domain('stock.picking', scope, [
                    ('state', 'not in', ('done', 'cancel')),
                    ('scheduled_date', '<', fields.Date.context_today(self)),
                ]),
                {'name': 'name', 'scheduled': 'scheduled_date', 'state': 'state'},
                'overdue_transfers', order='scheduled_date', date_fields=('scheduled_date',), scope=scope,
            ) if self._can_read('stock.picking') else [], 'overdue_transfers'),
            'pending_in': self._mgmt_table('Pending receipts', [
                {'key': 'name', 'label': 'Transfer'}, {'key': 'origin', 'label': 'Source'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'stock.picking',
                self._scope_domain('stock.picking', scope, [
                    ('picking_type_code', '=', 'incoming'), ('state', 'not in', ('done', 'cancel')),
                ]),
                {'name': 'name', 'origin': 'origin', 'state': 'state'},
                'pickings', order='scheduled_date', scope=scope,
            ) if self._can_read('stock.picking') else [], 'pickings'),
            'pending_out': self._mgmt_table('Pending deliveries', [
                {'key': 'name', 'label': 'Transfer'}, {'key': 'origin', 'label': 'Source'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'stock.picking',
                self._scope_domain('stock.picking', scope, [
                    ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel')),
                ]),
                {'name': 'name', 'origin': 'origin', 'state': 'state'},
                'pickings', order='scheduled_date', scope=scope,
            ) if self._can_read('stock.picking') else [], 'pickings'),
            'below_reorder': self._below_reorder_table(scope, reorder_data),
            'high_value': self._svl_high_value_table(scope),
            'gate_wait': self._mgmt_table('Gate passes waiting', [
                {'key': 'name', 'label': 'Pass'}, {'key': 'date', 'label': 'Date'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'ages.gate.pass',
                self._scope_domain('ages.gate.pass', scope, [('state', 'in', ('draft', 'waiting_security'))]) if self._can_read('ages.gate.pass') else [('id', '=', 0)],
                {'name': 'name', 'date': 'pass_date', 'state': 'state'},
                'gate_passes', order='pass_date', date_fields=('pass_date',), scope=scope,
            ) if self._can_read('ages.gate.pass') else [], 'gate_passes'),
            'overdue_rgp': self._mgmt_table('Overdue returnable gate passes', [
                {'key': 'name', 'label': 'Pass'}, {'key': 'date', 'label': 'Date'}, {'key': 'partner', 'label': 'Partner'},
            ], self._document_rows(
                'ages.gate.pass',
                self._scope_domain('ages.gate.pass', scope, [('return_state', '=', 'overdue')]) if self._has_field('ages.gate.pass', 'return_state') else [('id', '=', 0)],
                {'name': 'name', 'date': 'pass_date', 'partner': 'partner_id'},
                'gate_passes', order='pass_date', date_fields=('pass_date',), scope=scope,
            ) if self._can_read('ages.gate.pass') else [], 'gate_passes'),
            'consumption': self._mgmt_table('Material consumption register', [
                {'key': 'name', 'label': 'Document'}, {'key': 'date', 'label': 'Date'},
                {'key': 'project', 'label': 'Project'}, {'key': 'amount', 'label': 'Amount'},
            ], self._document_rows(
                'ages.material.consumption',
                self._scope_domain('ages.material.consumption', scope) + self._date_domain('date', date_from, date_to),
                {'name': 'name', 'date': 'date', 'project': 'project_id', 'amount': 'amount_total'},
                'material_consumption', order='date desc', money_fields=('amount_total',), date_fields=('date',), scope=scope,
            ) if self._can_read('ages.material.consumption') else [], 'material_consumption'),
            'quality_fail': self._mgmt_table('Failed quality checks', [
                {'key': 'name', 'label': 'Check'},
            ], self._document_rows(
                'quality.check',
                self._scope_domain('quality.check', scope, [('quality_state', '=', 'fail')]) if self._can_read('quality.check') and self._has_field('quality.check', 'quality_state') else [('id', '=', 0)],
                {'name': 'name'}, 'quality_checks', scope=scope,
            ) if self._can_read('quality.check') else [], 'quality_checks'),
            'orderpoints': self._orderpoint_table(scope),
        }
        warnings = [
            'Operational transfer dates prefer actual_date when that field exists.',
            'stock.quant.value is not aggregated. Accounting valuation is SVL only.',
            'Slow/dead stock is unavailable without a stored inbound age.',
        ]
        if svl_warning:
            warnings.append(svl_warning)
        return self._payload(
            scope, 'inventory', kpis, charts, tables,
            date_field='stock.picking.%s' % date_field, warnings=warnings,
            extra={'layout': self._dashboard_layout(
                kind='standard',
                hero=['qty', 'value', 'pending_in', 'negative', 'below_reorder', 'overdue_rgp'],
                charts=[('value_category', 8), ('warehouse', 4), ('movers', 6), ('gate_state', 6)],
                tables=['negative', 'below_reorder', 'overdue_rgp', 'consumption'],
            )},
        )

    def _negative_stock_table(self, scope):
        if not self._can_read('stock.quant'):
            return self._mgmt_table('Negative stock', [], [])
        rows = self._search_read(
            'stock.quant',
            self._scope_domain('stock.quant', scope) + [
                ('quantity', '<', 0), ('location_id.usage', '=', 'internal'),
            ],
            ['product_id', 'location_id', 'quantity'],
            limit=20, order='quantity',
        )
        table_rows = []
        for quant in rows:
            product = quant.get('product_id')
            location = quant.get('location_id')
            table_rows.append({
                'product': product[1] if product else '',
                'location': location[1] if location else '',
                'qty': quant.get('quantity'),
                'res_id': quant.get('id'),
                'action_key': 'stock_quants',
            })
        return self._mgmt_table('Negative stock', [
            {'key': 'product', 'label': 'Product'},
            {'key': 'location', 'label': 'Location'},
            {'key': 'qty', 'label': 'Qty'},
        ], table_rows, 'stock_quants')

    def _svl_high_value_table(self, scope):
        if not self._can_read('stock.valuation.layer'):
            return self._mgmt_table('High-value inventory (SVL)', [], [])
        groups = self.env['stock.valuation.layer'].read_group(
            self._scope_domain('stock.valuation.layer', scope),
            ['value:sum'], ['product_id'], lazy=False,
        )
        rows = []
        for group in sorted(groups, key=lambda item: abs(item.get('value') or 0.0), reverse=True)[:15]:
            product = group.get('product_id')
            rows.append({
                'product': product[1] if product else '',
                'value': self._format_money(group.get('value') or 0.0, scope),
                'res_id': product[0] if product else False,
                'res_field': 'product_id',
                'action_key': 'stock_quants',
            })
        return self._mgmt_table('High-value inventory (SVL remaining value)', [
            {'key': 'product', 'label': 'Product'}, {'key': 'value', 'label': 'Value'},
        ], rows, 'stock_quants')

    def _orderpoint_table(self, scope):
        if not self._can_read('stock.warehouse.orderpoint'):
            return self._mgmt_table('Reordering rules', [], [], 'orderpoints')
        rows = self._document_rows(
            'stock.warehouse.orderpoint',
            self._scope_domain('stock.warehouse.orderpoint', scope) if self._field_path_exists('stock.warehouse.orderpoint', 'company_id') else [],
            {'product': 'product_id', 'min': 'product_min_qty', 'max': 'product_max_qty'},
            'orderpoints', limit=20, scope=scope,
        )
        return self._mgmt_table('Reordering rules (stored min/max; on-hand is computed so not listed as a fact)', [
            {'key': 'product', 'label': 'Product'}, {'key': 'min', 'label': 'Min qty'}, {'key': 'max', 'label': 'Max qty'},
        ], rows, 'orderpoints')

    def _picking_trend_chart(self, scope, date_field, months=6):
        if not self._can_read('stock.picking'):
            return self._chart('bar', 'Incoming vs outgoing movement', [], [])
        buckets, date_to = self._month_starts(scope, months)
        labels, incoming, outgoing = [], [], []
        for month_start in buckets:
            month_end = min(fields.Date.end_of(month_start, 'month'), date_to)
            labels.append(month_start.strftime('%b %Y'))
            incoming.append(picking_domain_plus(self, self._scope_domain('stock.picking', scope), [
                ('picking_type_code', '=', 'incoming'), ('state', '=', 'done'),
            ], date_field, month_start, month_end))
            outgoing.append(picking_domain_plus(self, self._scope_domain('stock.picking', scope), [
                ('picking_type_code', '=', 'outgoing'), ('state', '=', 'done'),
            ], date_field, month_start, month_end))
        return self._chart('bar', 'Incoming vs outgoing movement', labels, [
            {'label': 'Receipts', 'data': incoming},
            {'label': 'Deliveries', 'data': outgoing},
        ])

    def _below_reorder_data(self, scope):
        if not self._can_read('stock.warehouse.orderpoint') or not self._can_read('stock.quant'):
            return {
                'available': False, 'reason': 'Reordering rules or quants are not readable.',
                'count': 0, 'rows': [],
            }
        if not self._has_field('stock.warehouse.orderpoint', 'product_min_qty'):
            return {
                'available': False, 'reason': 'product_min_qty is not stored on orderpoints.',
                'count': 0, 'rows': [],
            }
        if not self._has_field('stock.warehouse.orderpoint', 'qty_on_hand'):
            return {
                'available': False, 'reason': 'The standard orderpoint qty_on_hand field is unavailable.',
                'count': 0, 'rows': [],
            }
        points = self._search_read(
            'stock.warehouse.orderpoint',
            self._scope_domain('stock.warehouse.orderpoint', scope) if self._field_path_exists('stock.warehouse.orderpoint', 'company_id') else [],
            ['product_id', 'location_id', 'product_min_qty', 'qty_on_hand'],
            limit=200, order='id',
        )
        rows = []
        for point in points:
            product = point.get('product_id')
            location = point.get('location_id')
            if not product:
                continue
            on_hand = point.get('qty_on_hand') or 0.0
            minimum = point.get('product_min_qty') or 0.0
            if on_hand < minimum:
                rows.append({
                    'product': product[1] if product else '',
                    'location': location[1] if location else '',
                    'on_hand': round(on_hand, 2),
                    'min': minimum,
                    'res_id': point.get('id'),
                    'action_key': 'orderpoints',
                })
        return {'available': True, 'reason': '', 'count': len(rows), 'rows': rows}

    def _below_reorder_table(self, scope, data=None):
        data = data or self._below_reorder_data(scope)
        if not data['available']:
            return self._mgmt_table(
                'Below-reorder products', [], [], 'orderpoints', empty=data['reason']
            )
        rows = data['rows']
        return self._mgmt_table('Below-reorder products (standard availability vs stored min)', [
            {'key': 'product', 'label': 'Product'},
            {'key': 'location', 'label': 'Location'},
            {'key': 'on_hand', 'label': 'On hand'},
            {'key': 'min', 'label': 'Min'},
        ], rows[:20], 'orderpoints')


def picking_domain_plus(dashboard, base, extra, date_field, date_from, date_to):
    domain = list(base) + list(extra)
    if dashboard._field_path_exists('stock.picking', date_field):
        domain += dashboard._date_domain(date_field, date_from, date_to)
    return dashboard._search_count('stock.picking', domain)

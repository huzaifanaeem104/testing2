# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardSales(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_sales_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        if not self._capability_map().get('sale'):
            return self._unavailable(scope, 'sales', 'Salesperson or sales manager access is required.')
        date_from, date_to = scope['date_from'], scope['date_to']
        domain = self._scope_domain('sale.order', scope) + self._date_domain('date_order', date_from, date_to)
        quotations = self._search_count('sale.order', domain + [('state', 'in', ('draft', 'sent'))])
        confirmed = self._search_count('sale.order', domain + [('state', 'in', ('sale', 'done'))])
        cancelled = self._search_count('sale.order', domain + [('state', '=', 'cancel')])
        quote_value = self._read_group_sum('sale.order', domain + [('state', 'in', ('draft', 'sent'))], 'amount_untaxed')
        sale_value = self._read_group_sum('sale.order', domain + [('state', 'in', ('sale', 'done'))], 'amount_untaxed')
        qty_ordered = qty_delivered = qty_invoiced = 0.0
        so_values = {'ordered': 0.0, 'delivered': 0.0, 'invoiced': 0.0}
        if self._can_read('sale.order.line'):
            ld = self._scope_domain('sale.order.line', scope, [
                ('order_id.state', 'in', ('sale', 'done')),
            ])
            date_path = 'order_id.date_order' if self._field_path_exists('sale.order.line', 'order_id.date_order') else False
            if date_path:
                ld += self._date_domain(date_path, date_from, date_to)
            qty_ordered = self._read_group_sum('sale.order.line', ld, 'product_uom_qty')
            if self._has_field('sale.order.line', 'qty_delivered'):
                qty_delivered = self._read_group_sum('sale.order.line', ld, 'qty_delivered')
            if self._has_field('sale.order.line', 'qty_invoiced'):
                qty_invoiced = self._read_group_sum('sale.order.line', ld, 'qty_invoiced')
            so_values = self._so_line_values(scope, date_from, date_to)
        invoiced_value = 0.0
        paid_value = 0.0
        receivables = 0.0
        if self._can_read('account.move'):
            rec_domain = self._scope_domain('account.move', scope, [
                ('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
            ])
            invoiced_value = self._read_group_sum('account.move', rec_domain + self._date_domain('invoice_date', date_from, date_to), 'amount_total_signed')
            receivables = self._read_group_sum('account.move', rec_domain, 'amount_residual_signed')
            paid_value = abs((invoiced_value or 0.0) - (self._read_group_sum(
                'account.move', rec_domain + self._date_domain('invoice_date', date_from, date_to), 'amount_residual_signed'
            ) or 0.0))
        conversion = False
        if quotations + confirmed:
            conversion = 100.0 * confirmed / float(quotations + confirmed)
        stale = []
        stale_days = max(self._config_int('ages_enterprise_dashboard.stale_quotation_days', 14), 0)
        if quotations:
            stale_cut = fields.Date.context_today(self) - timedelta(days=stale_days)
            stale = self._search_read(
                'sale.order',
                domain + [('state', 'in', ('draft', 'sent')), ('date_order', '<=', '%s 00:00:00' % stale_cut)],
                ['name', 'partner_id', 'amount_untaxed', 'date_order'],
                limit=15, order='date_order',
            )
        overdue_pick = 0
        if self._can_read('stock.picking'):
            overdue_pick = self._search_count('stock.picking', self._scope_domain('stock.picking', scope, [
                ('picking_type_code', '=', 'outgoing'),
                ('state', 'not in', ('done', 'cancel')),
                ('scheduled_date', '<', fields.Date.context_today(self)),
            ]))
        kpis = [
            self._kpi(scope, 'quotations', 'Quotations', quotations, False, 'sale_orders', suffix='', basis='count'),
            self._kpi(scope, 'quote_value', 'Quotation value', quote_value, False, 'sale_orders'),
            self._kpi(scope, 'orders', 'Confirmed orders', confirmed, False, 'sale_orders', suffix='', basis='count'),
            self._kpi(scope, 'sale_value', 'Sales order value', sale_value, False, 'sale_orders'),
            self._kpi(scope, 'delivered_value', 'Delivered value', so_values.get('delivered') or 0.0, False, 'sale_order_lines',
                      'Confirmed SO line subtotal allocated by qty_delivered / product_uom_qty in the selected order date range.'),
            self._kpi(scope, 'invoiced_so_value', 'Invoiced SO value', so_values.get('invoiced') or 0.0, False, 'sale_order_lines',
                      'Confirmed SO line subtotal allocated by qty_invoiced / product_uom_qty.'),
            self._kpi(scope, 'cancelled', 'Cancelled orders', cancelled, False, 'sale_orders', suffix='', basis='count'),
            self._kpi(scope, 'qty_ordered', 'Qty ordered', qty_ordered, False, 'sale_orders', suffix='', basis='count'),
            self._kpi(scope, 'qty_delivered', 'Qty delivered', qty_delivered, False, 'sale_orders', suffix='', basis='count'),
            self._kpi(scope, 'qty_invoiced', 'Qty invoiced', qty_invoiced, False, 'sale_orders', suffix='', basis='count'),
            self._kpi(scope, 'invoiced_value', 'Customer invoice amount', invoiced_value, False, 'customer_invoices'),
            self._kpi(scope, 'paid_value', 'Invoiced minus residual (period invoices)', paid_value, False, 'customer_invoices',
                      'Period posted invoice totals minus remaining residual on those invoices. Not payment-matching.'),
            self._kpi(scope, 'receivables', 'Customer receivables', receivables, False, 'customer_invoices'),
            self._kpi(scope, 'conversion', 'Order conversion %', conversion if conversion is not False else 0.0, False, 'sale_orders',
                      'confirmed / (quotations + confirmed) in the period. Only defined when those states exist.', suffix='%', basis='ratio') if (quotations + confirmed) else self._unavailable_kpi(scope, 'conversion', 'Order conversion %', 'No quotations or confirmed orders in this period, so the denominator is empty.'),
            self._kpi(scope, 'overdue_do', 'Overdue deliveries', overdue_pick, False, 'pickings', suffix='', basis='count'),
        ]
        charts = {
            'states': self._group_chart('sale.order', domain, 'state', 'Order status'),
            'trend': self._chart('bar', 'Sales trend', *self._monthly_model_sum(
                'sale.order', scope, [('state', 'in', ('sale', 'done'))], 'date_order', 'amount_untaxed',
            )),
            'qty': self._chart('bar', 'Ordered vs delivered vs invoiced qty', ['Ordered', 'Delivered', 'Invoiced'], [
                {'label': 'Qty', 'data': [round(qty_ordered or 0.0, 2), round(qty_delivered or 0.0, 2), round(qty_invoiced or 0.0, 2)]},
            ]),
            'value': self._chart('bar', 'Ordered vs delivered vs invoiced value', ['Ordered', 'Delivered', 'Invoiced'], [
                {'label': 'Amount', 'data': [
                    round(so_values.get('ordered') or 0.0, 2),
                    round(so_values.get('delivered') or 0.0, 2),
                    round(so_values.get('invoiced') or 0.0, 2),
                ]},
            ]),
        }
        if self._has_field('sale.order', 'user_id'):
            charts['salespeople'] = self._group_chart('sale.order', domain + [('state', 'in', ('sale', 'done'))], 'user_id', 'Sales by salesperson', 'horizontalBar', value_field='amount_untaxed')
        if self._has_field('sale.order', 'team_id'):
            charts['teams'] = self._group_chart('sale.order', domain + [('state', 'in', ('sale', 'done'))], 'team_id', 'Sales by team', 'bar', value_field='amount_untaxed')
        if self._can_read('sale.order.line') and self._has_field('sale.order.line', 'product_id'):
            line_domain = self._scope_domain('sale.order.line', scope, [('order_id.state', 'in', ('sale', 'done'))])
            if self._field_path_exists('sale.order.line', 'order_id.date_order'):
                line_domain += self._date_domain('order_id.date_order', date_from, date_to)
            charts['products'] = self._group_chart('sale.order.line', line_domain, 'product_id', 'Sales by product', 'horizontalBar', value_field='price_subtotal' if self._has_field('sale.order.line', 'price_subtotal') else 'product_uom_qty')
        if self._can_read('account.move') and self._has_field('account.move', 'payment_state'):
            charts['payment'] = self._group_chart(
                'account.move',
                self._scope_domain('account.move', scope, [('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted')]),
                'payment_state', 'Invoice payment-state',
            )
        partner_rows = self.env['sale.order'].read_group(
            domain + [('state', 'in', ('sale', 'done'))], ['amount_untaxed:sum'], ['partner_id'], lazy=False,
        )
        partner_rows = sorted(partner_rows, key=lambda item: item.get('amount_untaxed') or 0.0, reverse=True)[:10]
        charts['customers'] = self._chart(
            'bar', 'Sales by customer',
            [(row.get('partner_id') or [False, 'Unknown'])[1] for row in partner_rows],
            [{'label': 'Untaxed', 'data': [round(row.get('amount_untaxed') or 0.0, 2) for row in partner_rows]}],
        )
        tables = {
            'orders': self._mgmt_table('Sales orders', [
                {'key': 'name', 'label': 'Order'}, {'key': 'partner', 'label': 'Customer'},
                {'key': 'state', 'label': 'State'}, {'key': 'amount', 'label': 'Untaxed'},
            ], self._document_rows(
                'sale.order', domain,
                {'name': 'name', 'partner': 'partner_id', 'state': 'state', 'amount': 'amount_untaxed'},
                'sale_orders', order='date_order desc', money_fields=('amount_untaxed',), scope=scope,
            ), 'sale_orders'),
            'stale': self._mgmt_table('Stale quotations', [
                {'key': 'name', 'label': 'Quotation'}, {'key': 'partner', 'label': 'Customer'}, {'key': 'amount', 'label': 'Untaxed'},
            ], [{
                'name': rec.get('name'),
                'partner': rec.get('partner_id')[1] if rec.get('partner_id') else '',
                'amount': self._format_money(rec.get('amount_untaxed') or 0.0, scope),
                'res_id': rec.get('id'),
                'action_key': 'sale_orders',
            } for rec in stale], 'sale_orders'),
            'customers': self._mgmt_table('Top customers', [
                {'key': 'name', 'label': 'Customer'}, {'key': 'amount', 'label': 'Untaxed'},
            ], [{
                'name': (row.get('partner_id') or [False, 'Unknown'])[1],
                'amount': self._format_money(row.get('amount_untaxed') or 0.0, scope),
                'res_id': (row.get('partner_id') or [False])[0],
                'res_field': 'partner_id',
                'action_key': 'sale_orders',
            } for row in partner_rows], 'sale_orders'),
            'overdue_do': self._mgmt_table('Overdue deliveries', [
                {'key': 'name', 'label': 'Transfer'}, {'key': 'scheduled', 'label': 'Scheduled'}, {'key': 'state', 'label': 'State'},
            ], self._document_rows(
                'stock.picking',
                self._scope_domain('stock.picking', scope, [
                    ('picking_type_code', '=', 'outgoing'),
                    ('state', 'not in', ('done', 'cancel')),
                    ('scheduled_date', '<', fields.Date.context_today(self)),
                ]) if self._can_read('stock.picking') else [('id', '=', 0)],
                {'name': 'name', 'scheduled': 'scheduled_date', 'state': 'state'},
                'pickings', order='scheduled_date', date_fields=('scheduled_date',), scope=scope,
            ) if self._can_read('stock.picking') else [], 'pickings'),
        }
        warnings = []
        if not confirmed and not quotations:
            warnings.append('No sales documents in this scope. Empty state is expected until orders exist.')
        sale_month = self._monthly_model_sum(
            'sale.order', scope, [('state', 'in', ('sale', 'done'))], 'date_order', 'amount_untaxed',
        )
        charts['trend'] = self._chart(
            'area', 'Confirmed sales by month', sale_month[0],
            [{'label': 'Untaxed', 'data': sale_month[1]}],
            unit='money', allow_toggle=True,
        )
        self._attach_sparklines(kpis, {'sale_value': (charts.get('trend'), 0, 'money')})
        extra = {'layout': self._dashboard_layout(
            kind='standard',
            hero=['orders', 'sale_value', 'quote_value', 'conversion', 'receivables', 'overdue_do'],
            charts=[('trend', 8), ('salespeople', 4), ('teams', 6), ('products', 6)],
            tables=['orders', 'stale', 'customers', 'overdue_do'],
        )}
        if conversion is not False:
            extra['progress'] = {'label': 'Order conversion', 'value': conversion}
        return self._payload(
            scope, 'sales', kpis, charts, tables,
            date_field='sale.order.date_order', warnings=warnings, extra=extra,
        )

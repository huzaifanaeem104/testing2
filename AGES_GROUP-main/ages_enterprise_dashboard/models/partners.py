# -*- coding: utf-8 -*-

from odoo import models


class AgesEnterpriseDashboardPartners(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_partners_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        caps = self._capability_map()
        if not (caps.get('sale') or caps.get('purchase') or caps.get('account') or caps.get('contract')):
            return self._unavailable(
                scope, 'partners',
                'Sale, purchase, accounting, or contract access is required.',
            )
        date_from, date_to = scope['date_from'], scope['date_to']
        kpis = []
        charts = {}
        tables = {}
        warnings = [
            'Customer and vendor chains use relational fields only. Name matching is not used.',
            'Select a customer or vendor filter to narrow a 360 view.',
        ]

        so_value = 0.0
        if self._can_read('sale.order'):
            so_value = self._read_group_sum(
                'sale.order',
                self._scope_domain('sale.order', scope, [('state', 'in', ('sale', 'done'))]) + self._date_domain('date_order', date_from, date_to),
                'amount_untaxed',
            )
            kpis.append(self._kpi(scope, 'ordered', 'Customer ordered (SO)', so_value, False, 'sale_orders'))
        qty_delivered = qty_invoiced = 0.0
        so_values = {'ordered': so_value or 0.0, 'delivered': 0.0, 'invoiced': 0.0}
        if self._can_read('sale.order.line'):
            ld = self._scope_domain('sale.order.line', scope, [
                ('order_id.state', 'in', ('sale', 'done')),
            ])
            if self._field_path_exists('sale.order.line', 'order_id.date_order'):
                ld += self._date_domain('order_id.date_order', date_from, date_to)
            if self._has_field('sale.order.line', 'qty_delivered'):
                qty_delivered = self._read_group_sum('sale.order.line', ld, 'qty_delivered')
            if self._has_field('sale.order.line', 'qty_invoiced'):
                qty_invoiced = self._read_group_sum('sale.order.line', ld, 'qty_invoiced')
            so_values = self._so_line_values(scope, date_from, date_to)
            kpis.append(self._kpi(scope, 'delivered_qty', 'Customer delivered qty', qty_delivered, False, 'sale_orders', suffix='', basis='count'))
            kpis.append(self._kpi(scope, 'delivered_value', 'Customer delivered value', so_values.get('delivered') or 0.0, False, 'sale_order_lines'))
            kpis.append(self._kpi(scope, 'invoiced_qty', 'Customer invoiced qty', qty_invoiced, False, 'sale_orders', suffix='', basis='count'))
        invoiced = residual = collections = 0.0
        if self._can_read('account.move'):
            rec = self._scope_domain('account.move', scope, [
                ('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
            ])
            invoiced = self._read_group_sum('account.move', rec + self._date_domain('invoice_date', date_from, date_to), 'amount_total_signed')
            residual = self._read_group_sum('account.move', rec, 'amount_residual_signed')
            kpis.extend([
                self._kpi(scope, 'invoiced', 'Customer invoiced', invoiced, False, 'customer_invoices'),
                self._kpi(scope, 'outstanding_ar', 'Customer outstanding', residual, False, 'customer_invoices'),
            ])
        collections = self._payment_sum(scope, 'inbound', date_from, date_to)
        kpis.append(self._kpi(scope, 'collected', 'Customer collections', collections, False, 'payments'))

        requested = ordered = received = billed = paid = outstanding_ap = 0.0
        if self._can_read('purchase.request') and self._has_field('purchase.request', 'estimated_cost'):
            requested = self._read_group_sum(
                'purchase.request',
                self._scope_domain('purchase.request', scope) + self._date_domain('date_start', date_from, date_to),
                'estimated_cost',
            )
            kpis.append(self._kpi(scope, 'requested', 'Vendor requested (PR)', requested, False, 'purchase_requests'))
        if self._can_read('purchase.order'):
            ordered = self._read_group_sum(
                'purchase.order',
                self._scope_domain('purchase.order', scope, [('state', 'in', ('purchase', 'done'))]) + self._date_domain('date_order', date_from, date_to),
                'amount_untaxed',
            )
            kpis.append(self._kpi(scope, 'po_ordered', 'Vendor ordered (PO)', ordered, False, 'purchase_orders'))
        if self._can_read('purchase.order.line') and self._has_field('purchase.order.line', 'qty_received'):
            po_values = self._po_line_values(scope, date_from, date_to)
            received = po_values.get('received') or 0.0
            kpis.append(self._kpi(scope, 'received_qty', 'Vendor received qty', self._read_group_sum(
                'purchase.order.line',
                self._scope_domain('purchase.order.line', scope, [('order_id.state', 'in', ('purchase', 'done'))]) + (
                    self._date_domain('order_id.date_order', date_from, date_to)
                    if self._field_path_exists('purchase.order.line', 'order_id.date_order') else []
                ),
                'qty_received',
            ), False, 'purchase_orders', suffix='', basis='count'))
            kpis.append(self._kpi(scope, 'received_value', 'Vendor received value', received, False, 'purchase_orders',
                                  'Confirmed PO line subtotal allocated by qty_received / product_qty in the selected order date range.'))
        if self._can_read('account.move'):
            pay = self._scope_domain('account.move', scope, [
                ('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted'),
            ])
            billed = abs(self._read_group_sum('account.move', pay + self._date_domain('invoice_date', date_from, date_to), 'amount_total_signed') or 0.0)
            outstanding_ap = abs(self._read_group_sum('account.move', pay, 'amount_residual_signed') or 0.0)
            kpis.extend([
                self._kpi(scope, 'billed', 'Vendor billed', billed, False, 'vendor_bills'),
                self._kpi(scope, 'outstanding_ap', 'Vendor outstanding', outstanding_ap, False, 'vendor_bills'),
            ])
        paid = self._payment_sum(scope, 'outbound', date_from, date_to)
        kpis.append(self._kpi(scope, 'vendor_paid', 'Vendor payments', paid, False, 'payments'))

        contract_value = ra_work = invoice_value = backlog = collected = outstanding_ra = 0.0
        if self._can_read('ages.contract'):
            contract_value = self._read_group_sum('ages.contract', self._scope_domain('ages.contract', scope), 'total_work_done_value')
            kpis.append(self._kpi(scope, 'contract_value', 'Contract value', contract_value, False, 'contracts'))
        if self._can_read('ages.running.bill'):
            ra_work = self._read_group_sum(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [('state', '!=', 'cancelled')]),
                'value_of_work_done',
            )
            invoice_value = self._read_group_sum(
                'ages.running.bill',
                self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')]) + self._date_domain('date', date_from, date_to),
                'total_receivable',
            )
            backlog = max((contract_value or 0.0) - (ra_work or 0.0), 0.0)
            if self._has_field('ages.running.bill', 'invoice_payment_state'):
                collected = self._read_group_sum(
                    'ages.running.bill',
                    self._scope_domain('ages.running.bill', scope, [
                        ('state', '=', 'confirmed'),
                        ('invoice_payment_state', '=', 'paid'),
                    ]),
                    'total_receivable',
                )
                outstanding_ra = self._read_group_sum(
                    'ages.running.bill',
                    self._scope_domain('ages.running.bill', scope, [
                        ('state', '=', 'confirmed'),
                        ('invoice_payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
                    ]),
                    'total_receivable',
                )
            kpis.extend([
                self._kpi(scope, 'ra_work', 'Cumulative RA work', ra_work, False, 'running_bills'),
                self._kpi(scope, 'ra_invoice', 'Period RA receivable', invoice_value, False, 'running_bills'),
                self._kpi(scope, 'ra_collected', 'Collected RA invoices', collected, False, 'running_bills',
                          'Confirmed RA total_receivable where stored invoice_payment_state is paid.') if self._has_field('ages.running.bill', 'invoice_payment_state') else self._unavailable_kpi(scope, 'ra_collected', 'Collected RA invoices', 'invoice_payment_state is not present on ages.running.bill.'),
                self._kpi(scope, 'ra_outstanding', 'Outstanding RA invoices', outstanding_ra, False, 'unpaid_ra') if self._has_field('ages.running.bill', 'invoice_payment_state') else self._unavailable_kpi(scope, 'ra_outstanding', 'Outstanding RA invoices', 'invoice_payment_state is not present on ages.running.bill.'),
                self._kpi(scope, 'backlog', 'Contract backlog', backlog, False, 'contracts'),
            ])

        charts['customer'] = self._chart('horizontalBar', 'Customer chain', ['Ordered', 'Delivered', 'Invoiced', 'Collected', 'Outstanding'], [
            {'label': 'Amount', 'data': [
                round(so_value or 0.0, 2), round(so_values.get('delivered') or 0.0, 2),
                round(invoiced or 0.0, 2), round(collections or 0.0, 2), round(residual or 0.0, 2),
            ]},
        ], unit='money')
        charts['vendor'] = self._chart('horizontalBar', 'Vendor chain', ['Requested', 'Ordered', 'Received', 'Billed', 'Paid', 'Outstanding'], [
            {'label': 'Amount', 'data': [
                round(requested or 0.0, 2), round(ordered or 0.0, 2), round(received or 0.0, 2),
                round(billed or 0.0, 2), round(paid or 0.0, 2), round(outstanding_ap or 0.0, 2),
            ]},
        ], unit='money')
        charts['contract'] = self._chart('horizontalBar', 'Contract chain', ['Value', 'RA work', 'Period receivable', 'Collected', 'Backlog'], [
            {'label': 'Amount', 'data': [
                round(contract_value or 0.0, 2), round(ra_work or 0.0, 2),
                round(invoice_value or 0.0, 2), round(collected or 0.0, 2), round(backlog or 0.0, 2),
            ]},
        ], unit='money')
        tables['overdue_customers'] = self._overdue_partner_table(scope, 'out_invoice', 'Customer outstanding', 'overdue_invoices')
        tables['overdue_vendors'] = self._overdue_partner_table(scope, 'in_invoice', 'Vendor outstanding', 'overdue_bills')
        if scope.get('employee_ids') and self._can_read('hr.attendance'):
            att_domain = self._scope_domain('hr.attendance', scope)
            if date_from:
                att_domain.append(('check_in', '>=', '%s 00:00:00' % date_from))
            if date_to:
                att_domain.append(('check_in', '<=', '%s 23:59:59' % date_to))
            hours = self._read_group_sum('hr.attendance', att_domain, 'worked_hours') if self._has_field('hr.attendance', 'worked_hours') else 0.0
            kpis.append(self._kpi(scope, 'emp_hours', 'Employee attendance hours', hours, False, 'attendances', suffix='', basis='count'))
            if self._capability_map().get('payroll'):
                payroll = self._read_group_sum(
                    'hr.payslip',
                    self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))]) + self._date_domain('date_from', date_from, date_to),
                    'net_wage',
                )
                kpis.append(self._kpi(scope, 'emp_payroll', 'Employee payroll net', payroll, False, 'payslips'))
        elif self._can_read('hr.employee'):
            kpis.append(self._unavailable_kpi(
                scope, 'emp_hours', 'Employee chain hours',
                'Select an employee filter to load attendance hours and payroll cost for that person.',
            ))
        extra = {
            'layout': self._dashboard_layout(
                kind='standard',
                hero=['ordered', 'delivered_value', 'ra_work', 'backlog'],
                charts=[('customer', 12), ('vendor', 6), ('contract', 6)],
                tables=['overdue_customers', 'overdue_vendors'],
            ),
        }
        if not scope.get('partner_ids') and not scope.get('vendor_ids'):
            extra['scoped_note'] = 'Select a customer or vendor to narrow the 360 view.'
        return self._payload(
            scope, 'partners', kpis, charts, tables,
            date_field='mixed', warnings=warnings, extra=extra,
        )

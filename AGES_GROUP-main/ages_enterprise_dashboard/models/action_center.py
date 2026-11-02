# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class AgesEnterpriseDashboardActionCenter(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def _queue_group(self, key):
        cash = {
            'overdue_invoices', 'overdue_bills', 'unposted', 'unreconciled', 'je_validate',
            'pending_payments', 'unpaid_ra', 'followup_actions', 'payslip_link',
        }
        delivery = {
            'overdue_receipts', 'pending_pr', 'pending_pr_qty', 'delayed_pr', 'pending_po_qty',
            'draft_consumption', 'gate_pass', 'overdue_rgp', 'negative_stock', 'low_stock',
            'pending_deliveries', 'quality_pending', 'quality_fail',
        }
        people = {
            'draft_payslips', 'portal_sync', 'we_conflict', 'we_draft', 'overdue_loans',
            'pending_leave', 'missing_checkout', 'leave_payroll_blocked',
        }
        if key in cash:
            return 'cash'
        if key in delivery:
            return 'delivery'
        if key in people:
            return 'people'
        return 'commercial'

    def _action_center_queues(self, scope):
        today = fields.Date.context_today(self)
        grace = self._config_int('ages_enterprise_dashboard.overdue_grace_days', 0)
        overdue_cutoff = today - timedelta(days=grace) if grace else today
        expiry_days = self._config_int('ages_enterprise_dashboard.contract_expiry_days', 30)
        close_horizon = today + timedelta(days=expiry_days)
        critical_count = max(self._config_int('ages_enterprise_dashboard.critical_queue_count', 10), 1)
        queues = []

        def add(key, title, model_name, domain, action_key, why, severity='warning',
                date_field=False, amount_field=False, abs_amount=False, quantity=False):
            if not self._can_read(model_name):
                return
            if date_field and not self._field_path_exists(model_name, date_field):
                date_field = False
            if amount_field and not self._has_field(model_name, amount_field):
                amount_field = False
            full = self._scope_domain(model_name, scope, domain)
            count = self._search_count(model_name, full)
            amount = 0.0
            if amount_field:
                amount = self._read_group_sum(model_name, full, amount_field) or 0.0
                if abs_amount:
                    amount = abs(amount)
            oldest_days = False
            oldest_date = False
            if date_field and count:
                oldest = self._search_read(model_name, full, [date_field], limit=1, order='%s, id' % date_field)
                if oldest and oldest[0].get(date_field):
                    oldest_date = oldest[0].get(date_field)
                    if hasattr(oldest_date, 'date'):
                        oldest_date = oldest_date.date()
                    try:
                        oldest_days = max((today - oldest_date).days, 0)
                    except Exception:
                        oldest_days = False
            read_fields = ['name', 'display_name']
            if date_field:
                read_fields.append(date_field)
            items = self._search_read(model_name, full, read_fields, limit=8, order=('%s, id' % date_field) if date_field else 'id')
            if amount_field:
                amount_formatted = (
                    self._format_kpi_value(amount, scope, 'count')
                    if quantity else self._format_money(amount, scope)
                )
            else:
                amount_formatted = False
            queues.append({
                'key': key,
                'title': title,
                'count': count,
                'amount': amount,
                'amount_formatted': amount_formatted,
                'oldest_days': oldest_days,
                'oldest_date': self._format_date(oldest_date) if oldest_date else False,
                'why': why,
                'severity': 'danger' if count >= critical_count or severity == 'danger' else severity,
                'action_key': action_key,
                'model': model_name,
                'group': self._queue_group(key),
                'items': [{
                    'id': item.get('id'),
                    'name': item.get('display_name') or item.get('name') or '#%s' % item.get('id'),
                } for item in items],
            })

        add('overdue_invoices', 'Overdue customer invoices', 'account.move', [
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', overdue_cutoff),
        ], 'overdue_invoices',
            'Posted unpaid/partial customer invoices past invoice_date_due. Cash not yet collected.',
            'danger', date_field='invoice_date_due', amount_field='amount_residual_signed', abs_amount=True)
        add('overdue_bills', 'Overdue vendor bills', 'account.move', [
            ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')), ('invoice_date_due', '<', overdue_cutoff),
        ], 'overdue_bills',
            'Posted unpaid/partial vendor bills past due. Retention residual is still on those bills.',
            'danger', date_field='invoice_date_due', amount_field='amount_residual_signed', abs_amount=True)
        add('unposted', 'Unposted journal entries', 'account.move', [('state', '=', 'draft')],
            'unposted_moves', 'Draft account.move records are not posted actuals.',
            date_field='date', amount_field='amount_total_signed', abs_amount=True)
        if self._has_field('account.move.line', 'reconciled'):
            add('unreconciled', 'Unreconciled journal items', 'account.move.line', [
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('account_id.reconcile', '=', True),
                ('amount_residual', '!=', 0),
            ], 'unreconciled',
                'Posted reconcile-able AML still carrying a residual.',
                date_field='date', amount_field='amount_residual', abs_amount=True)
        if self._has_field('account.move', 'je_stage'):
            add('je_validate', 'Journal entries awaiting validation', 'account.move',
                [('je_stage', '=', 'validate')], 'je_validate',
                'Moves sitting in je_stage validate before posting.',
                date_field='date', amount_field='amount_total_signed', abs_amount=True)
        if self._has_field('account.payment', 'validation_status'):
            add('pending_payments', 'Payments pending approval', 'account.payment',
                [('validation_status', 'in', ('waiting', 'pending'))], 'pending_payments',
                'Tier validation has not approved these payments.',
                date_field='date', amount_field='amount')
        if self._has_field('purchase.request', 'validation_status'):
            add('pending_pr', 'Purchase requests pending approval', 'purchase.request',
                [('validation_status', 'in', ('waiting', 'pending'))], 'pending_pr',
                'Purchase requests waiting on tier validation.',
                date_field='date_start')
        if self._can_read('stock.picking'):
            date_field = 'scheduled_date'
            add('overdue_receipts', 'Overdue purchase receipts', 'stock.picking', [
                ('picking_type_code', '=', 'incoming'),
                ('state', 'not in', ('done', 'cancel')),
                ('scheduled_date', '<', '%s 23:59:59' % today),
            ], 'overdue_receipts',
                'Incoming transfers not done/cancelled whose scheduled_date is past due.',
                'danger', date_field=date_field)
        add('draft_ra', 'Draft running bills', 'ages.running.bill', [('state', '=', 'draft')],
            'draft_running_bills', 'RA documents not yet confirmed, so they are excluded from billed work.',
            date_field='date', amount_field='net_amount')
        if self._has_field('ages.running.bill', 'invoice_payment_state'):
            add('unpaid_ra', 'RA invoices unpaid or partial', 'ages.running.bill', [
                ('state', '=', 'confirmed'),
                ('invoice_payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
            ], 'unpaid_ra',
                'Confirmed RA whose linked invoice is not fully paid.',
                'danger', date_field='date', amount_field='net_amount')
        if self._has_field('ages.running.bill', 'invoice_id'):
            add('missing_ra_invoice', 'Confirmed RA missing an invoice', 'ages.running.bill', [
                ('state', '=', 'confirmed'), ('invoice_id', '=', False),
            ], 'missing_ra_invoices',
                'Confirmed running bills with no invoice_id. Collections cannot follow the RA invoice.',
                date_field='date', amount_field='net_amount')
        if self._has_field('ages.contract', 'date_close'):
            add('expiring_contracts', 'Contracts near close date', 'ages.contract', [
                ('state', 'in', ('new', 'running')),
                ('date_close', '!=', False),
                ('date_close', '<=', close_horizon),
            ], 'expiring_contracts',
                'Open contracts whose date_close is inside the configured horizon.',
                date_field='date_close', amount_field='total_work_done_value')
        if self._can_read('project.task') and self._has_field('project.task', 'date_deadline'):
            add('overdue_tasks', 'Overdue project tasks', 'project.task', [
                ('date_deadline', '<', today),
                ('state', 'not in', ('1_done', '1_canceled')),
            ], 'overdue_tasks',
                'Open tasks whose date_deadline is before today.',
                'danger', date_field='date_deadline')
        add('draft_consumption', 'Incomplete material consumption', 'ages.material.consumption',
            [('state', 'in', ('draft', 'confirmed'))], 'incomplete_consumption',
            'Consumption documents not yet done, so they are not site actuals.',
            date_field='date', amount_field='amount_total')
        if self._has_field('ages.gate.pass', 'state'):
            waiting_states = ['draft']
            try:
                selection = self.env['ages.gate.pass']._fields['state'].selection
                if callable(selection):
                    selection = selection(self.env['ages.gate.pass'])
                if 'waiting_security' in dict(selection or []):
                    waiting_states.append('waiting_security')
            except Exception:
                pass
            add('gate_pass', 'Gate passes waiting', 'ages.gate.pass',
                [('state', 'in', tuple(waiting_states))], 'waiting_gate_passes',
                'Gate passes still in draft or waiting security.',
                date_field='pass_date')
        if self._has_field('ages.gate.pass', 'return_state'):
            add('overdue_rgp', 'Overdue returnable gate passes', 'ages.gate.pass',
                [('return_state', '=', 'overdue')], 'overdue_rgp',
                'Returnable gate passes marked overdue by the gate-pass workflow.',
                'danger', date_field='pass_date')
        add('draft_payslips', 'Draft payslips', 'hr.payslip', [('state', 'in', ('draft', 'verify'))],
            'draft_payslips', 'Payslips not finalized; payroll cost KPIs exclude them.',
            date_field='date_from', amount_field='net_wage')
        if self._can_read('project.portal.attendance') and self._has_field('project.portal.attendance', 'sync_state'):
            add('portal_sync', 'Portal attendance sync failures', 'project.portal.attendance',
                [('sync_state', '=', 'failed')], 'portal_sync_failures',
                'Portal rows that failed to sync into hr.attendance.',
                'danger', date_field='date')
        if self._can_read('hr.work.entry') and self._has_field('hr.work.entry', 'state'):
            add('we_conflict', 'Work entry conflicts', 'hr.work.entry',
                [('state', '=', 'conflict')], 'work_entry_conflicts_all',
                'Work entries in conflict state block clean payroll time.',
                'danger', date_field='date_start')
        if self._can_read('purchase.request.line') and self._has_field('purchase.request.line', 'pending_qty_to_receive'):
            add('pending_pr_qty', 'PR quantities pending receipt', 'purchase.request.line',
                [('pending_qty_to_receive', '>', 0)], 'pending_pr_qty',
                'Stored pending_qty_to_receive on purchase.request.line.',
                date_field='date_required', amount_field='pending_qty_to_receive', quantity=True)
        if self._can_read('quality.check') and self._has_field('quality.check', 'quality_state'):
            add('quality_pending', 'Pending quality checks', 'quality.check',
                [('quality_state', 'not in', ('pass', 'fail'))], 'quality_pending',
                'Quality checks not yet passed or failed.')
            add('quality_fail', 'Failed quality checks', 'quality.check',
                [('quality_state', '=', 'fail')], 'quality_failed',
                'Quality checks recorded as fail.',
                'danger')
        if self._can_read('stock.picking'):
            add('pending_deliveries', 'Pending deliveries', 'stock.picking', [
                ('picking_type_code', '=', 'outgoing'),
                ('state', 'not in', ('done', 'cancel')),
            ], 'pending_deliveries',
                'Outgoing transfers not done or cancelled.',
                date_field='scheduled_date')
        if self._can_read('purchase.request.line') and self._has_field('purchase.request.line', 'date_required'):
            extra_qty = [('date_required', '<', today)]
            if self._has_field('purchase.request.line', 'pending_qty_to_receive'):
                extra_qty.append(('pending_qty_to_receive', '>', 0))
            else:
                if self._has_field('purchase.request.line', 'cancelled'):
                    extra_qty.append(('cancelled', '=', False))
                if self._has_field('purchase.request.line', 'request_state'):
                    extra_qty.append(('request_state', 'not in', ('done', 'rejected', 'cancelled', 'cancel')))
            add('delayed_pr', 'Delayed purchase request lines', 'purchase.request.line', extra_qty,
                'delayed_pr_lines',
                'PR lines whose date_required is past and quantity is still pending.',
                'danger', date_field='date_required')
        if self._can_read('hr.loan.installment'):
            add('overdue_loans', 'Overdue loan installments', 'hr.loan.installment',
                [('due_date', '<', today), ('deduction_state', 'in', ('pending', 'partial'))], 'overdue_loan_installments',
                'Loan installments past due_date that are not fully deducted.',
                'danger', date_field='due_date', amount_field='amount_residual')
        if self._can_read('hr.work.entry') and self._has_field('hr.work.entry', 'state'):
            add('we_draft', 'Draft work entries', 'hr.work.entry',
                [('state', '=', 'draft')], 'draft_work_entries_all',
                'Work entries not validated. Missing calendar rows are not invented.',
                date_field='date_start')
        if self._can_read('stock.quant'):
            add('negative_stock', 'Negative stock quants', 'stock.quant',
                [('quantity', '<', 0), ('location_id.usage', '=', 'internal')], 'negative_stock',
                'Internal stock showing a negative quantity.',
                'danger', amount_field='quantity', quantity=True)
        if self._can_read('hr.leave') and self._has_field('hr.leave', 'state'):
            leave_states = dict(self.env['hr.leave']._fields['state'].selection or [])
            leave_domain = [('state', 'in', ('confirm', 'validate1'))] if 'validate1' in leave_states else [('state', '=', 'confirm')]
            add('pending_leave', 'Time off awaiting approval', 'hr.leave', leave_domain,
                'pending_leave',
                'Leave requests not yet validated. Payroll holiday blocks are a separate module.',
                date_field='date_from')
        if self._can_read('hr.attendance'):
            add('missing_checkout', 'Missing check-outs', 'hr.attendance',
                [('check_out', '=', False)], 'missing_checkouts_all',
                'Attendance rows still open with no check_out. Period filter is not applied; this is a live exception.',
                date_field='check_in')
        if self._can_read('hr.payslip') and self._has_field('hr.payslip', 'move_id') and self._capability_map().get('payroll'):
            add('payslip_link', 'Payslips missing journal entry', 'hr.payslip',
                [('state', 'in', ('done', 'paid')), ('move_id', '=', False)], 'payslips_missing_move_all',
                'Finalized payslips with no accounting move_id.',
                date_field='date_from', amount_field='net_wage')
        if self._can_read('purchase.order') and self._has_field('purchase.order', 'receipt_status'):
            add('pending_po_qty', 'Purchase orders pending receipt', 'purchase.order', [
                ('state', 'in', ('purchase', 'done')),
                ('receipt_status', 'in', ('pending', 'partial')),
            ], 'pending_po_receipts',
                'Confirmed POs whose receipt_status is pending or partial.',
                date_field='date_order', amount_field='amount_untaxed')
        reorder_data = self._below_reorder_data(scope)
        if reorder_data.get('available') and reorder_data.get('count'):
            queues.append({
                'key': 'low_stock',
                'title': 'Below-reorder products',
                'count': reorder_data['count'],
                'amount': 0.0,
                'amount_formatted': False,
                'oldest_days': False,
                'oldest_date': False,
                'why': 'Standard orderpoint qty_on_hand is below stored product_min_qty.',
                'severity': 'danger' if reorder_data['count'] >= critical_count else 'warning',
                'action_key': 'below_reorder',
                'model': 'stock.warehouse.orderpoint',
                'group': self._queue_group('low_stock'),
                'items': [{
                    'id': row.get('res_id'),
                    'name': row.get('product') or '#%s' % row.get('res_id'),
                } for row in (reorder_data.get('rows') or [])[:8]],
            })
        if self._can_read('asset.transfer') and self._has_field('asset.transfer', 'state'):
            add('asset_transfers', 'Open asset transfers', 'asset.transfer',
                [('state', 'not in', ('done', 'cancelled'))], 'asset_transfers',
                'Asset transfers not completed.')
        if self._has_field('hr.leave', 'payslip_state'):
            add('leave_payroll_blocked', 'Leave blocked from current payroll', 'hr.leave',
                [('payslip_state', '=', 'blocked')], 'leave_payroll_blocked',
                'Validated leave whose stored payslip_state is blocked (defer to next payslip).',
                'danger', date_field='date_from')
        if self._has_field('res.partner', 'payment_next_action_date'):
            add('followup_actions', 'Follow-up next actions due', 'res.partner',
                [('payment_next_action_date', '!=', False), ('payment_next_action_date', '<=', today)],
                'followup_partners',
                'Partners whose stored payment_next_action_date is today or earlier. Follow-up level itself is computed and is not aggregated.',
                date_field='payment_next_action_date')
        if self._capability_map().get('audit'):
            audit_domain = self._typed_date_domain(
                'ages.deletion.audit', 'create_date',
                scope.get('date_from'), scope.get('date_to'),
            )
            add('deletion_audit', 'Deletion audit activity', 'ages.deletion.audit',
                audit_domain, 'deletion_audit',
                'Stored deletion-audit rows in the selected create_date range when ages_deletion_audit is authorized.',
                date_field='create_date')

        return queues

    def get_action_center_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        queues = self._action_center_queues(scope)
        open_queues = [queue for queue in queues if queue['count']]
        cleared = [queue for queue in queues if not queue['count']]
        money_at_risk = sum(queue.get('amount') or 0.0 for queue in open_queues)
        oldest = max((queue.get('oldest_days') or 0) for queue in open_queues) if open_queues else 0
        severity_counts = {'danger': 0, 'warning': 0, 'info': 0}
        for queue in open_queues:
            key = queue.get('severity') if queue.get('severity') in severity_counts else 'warning'
            severity_counts[key] += 1
        kpis = [
            self._kpi(scope, 'queues', 'Open queues', len(open_queues), False, False,
                      'Number of exception queues that currently have records.',
                      suffix='', basis='count', formula='COUNT queues with count > 0.'),
            self._kpi(scope, 'items', 'Records needing action', sum(queue['count'] for queue in open_queues), False, False,
                      'Sum of records across open exception queues.',
                      suffix='', basis='count', formula='SUM(open queue counts).'),
            self._kpi(scope, 'money_risk', 'Money at risk', money_at_risk, False, False,
                      'Sum of stored queue amounts on open queues only.'),
            self._kpi(scope, 'oldest', 'Oldest open item (days)', oldest, False, False,
                      'Maximum oldest_days among open queues.',
                      suffix='', basis='count'),
        ]
        charts = {
            'severity': self._chart(
                'doughnut', 'Open queues by severity',
                ['Critical', 'Warning', 'Info'],
                [{'label': 'Queues', 'data': [
                    severity_counts['danger'], severity_counts['warning'], severity_counts['info'],
                ]}],
                unit='count', size='sm',
            ),
        }
        return self._payload(
            scope, 'action_center', kpis, charts, {},
            alerts=open_queues,
            extra={
                'queues': open_queues,
                'cleared': cleared,
                'layout': self._dashboard_layout(
                    kind='queues',
                    hero=['queues', 'items', 'money_risk', 'oldest'],
                    charts=[('severity', 4)],
                    alerts=[queue['key'] for queue in open_queues],
                ),
            },
        )

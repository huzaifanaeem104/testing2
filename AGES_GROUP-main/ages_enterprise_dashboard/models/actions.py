# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, models
from odoo.osv import expression


class AgesEnterpriseDashboardActions(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def _action_specs(self):
        return {
            'aml_income': {
                'model': 'account.move.line',
                'name': 'Income lines',
                'views': [[False, 'list'], [False, 'form']],
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', 'in', ('income', 'income_other')),
                ],
                'date_field': 'date',
            },
            'aml_expense': {
                'model': 'account.move.line',
                'name': 'Expense lines',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation')),
                ],
                'date_field': 'date',
            },
            'aml_cash': {
                'model': 'account.move.line',
                'name': 'Cash and bank lines',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', '=', 'asset_cash'),
                ],
                'date_field': 'date',
            },
            'aml_cash_snapshot': {
                'model': 'account.move.line',
                'name': 'Cash and bank position',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', '=', 'asset_cash'),
                ],
                'through_date_field': 'date',
            },
            'aml_bank_snapshot': {
                'model': 'account.move.line',
                'name': 'Bank position',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', '=', 'asset_cash'),
                    ('journal_id.type', '=', 'bank'),
                ],
                'through_date_field': 'date',
            },
            'aml_cash_hand_snapshot': {
                'model': 'account.move.line',
                'name': 'Cash position',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', '=', 'asset_cash'),
                    ('journal_id.type', '=', 'cash'),
                ],
                'through_date_field': 'date',
            },
            'cash_inflow': {
                'model': 'account.move.line',
                'name': 'Cash inflow',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', '=', 'asset_cash'),
                    ('debit', '>', 0),
                ],
                'date_field': 'date',
            },
            'cash_outflow': {
                'model': 'account.move.line',
                'name': 'Cash outflow',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('display_type', 'not in', ('line_section', 'line_note')),
                    ('account_id.account_type', '=', 'asset_cash'),
                    ('credit', '>', 0),
                ],
                'date_field': 'date',
            },
            'vendor_retention_lines': {
                'model': 'account.move.line',
                'name': 'Open vendor retention lines',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('ages_is_vendor_retention_line', '=', True),
                    ('amount_residual', '!=', 0),
                ],
            },
            'customer_invoices': {
                'model': 'account.move',
                'name': 'Customer invoices',
                'extra': [('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted')],
                'date_field': 'invoice_date',
            },
            'vendor_bills': {
                'model': 'account.move',
                'name': 'Vendor bills',
                'extra': [('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted')],
                'date_field': 'invoice_date',
            },
            'customer_receivables': {
                'model': 'account.move',
                'name': 'Open customer receivables',
                'extra': [
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                    ('state', '=', 'posted'),
                    ('amount_residual_signed', '!=', 0),
                ],
            },
            'vendor_payables': {
                'model': 'account.move',
                'name': 'Open vendor payables',
                'extra': [
                    ('move_type', 'in', ('in_invoice', 'in_refund')),
                    ('state', '=', 'posted'),
                    ('amount_residual_signed', '!=', 0),
                ],
            },
            'overdue_invoices': {
                'model': 'account.move',
                'name': 'Overdue customer invoices',
                'extra': [
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                    ('invoice_date_due', '<', False),
                ],
                'due_before_today': True,
            },
            'overdue_bills': {
                'model': 'account.move',
                'name': 'Overdue vendor bills',
                'extra': [
                    ('move_type', '=', 'in_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                ],
                'due_before_today': True,
            },
            'unposted_moves': {
                'model': 'account.move',
                'name': 'Unposted journal entries',
                'extra': [('state', '=', 'draft')],
            },
            'je_validate': {
                'model': 'account.move',
                'name': 'Journal entries awaiting validation',
                'extra': [('je_stage', '=', 'validate')],
            },
            'payments': {
                'model': 'account.payment',
                'name': 'Payments',
                'date_field': 'date',
            },
            'customer_collections': {
                'model': 'account.payment',
                'name': 'Customer collections',
                'extra': [
                    ('payment_type', '=', 'inbound'),
                    ('state', 'in', ('paid', 'in_process')),
                    ('is_internal_transfer', '=', False),
                ],
                'date_field': 'date',
            },
            'vendor_payments': {
                'model': 'account.payment',
                'name': 'Vendor payments',
                'extra': [
                    ('payment_type', '=', 'outbound'),
                    ('state', 'in', ('paid', 'in_process')),
                    ('is_internal_transfer', '=', False),
                ],
                'date_field': 'date',
            },
            'pending_payments': {
                'model': 'account.payment',
                'name': 'Payments pending approval',
                'extra': [('validation_status', 'in', ('waiting', 'pending'))],
            },
            'contracts': {
                'model': 'ages.contract',
                'name': 'Contracts',
            },
            'running_bills': {
                'model': 'ages.running.bill',
                'name': 'Running bills',
                'date_field': 'date',
            },
            'draft_running_bills': {
                'model': 'ages.running.bill',
                'name': 'Draft running bills',
                'extra': [('state', '=', 'draft')],
            },
            'projects': {
                'model': 'project.project',
                'name': 'Projects',
            },
            'project_tasks': {
                'model': 'project.task',
                'name': 'Project tasks',
            },
            'overdue_tasks': {
                'model': 'project.task',
                'name': 'Overdue tasks',
                'extra': [('date_deadline', '<', False), ('state', 'not in', ('1_done', '1_canceled'))],
                'deadline_before_today': True,
            },
            'purchase_orders': {
                'model': 'purchase.order',
                'name': 'Purchase orders',
                'date_field': 'date_order',
            },
            'purchase_order_lines': {
                'model': 'purchase.order.line',
                'name': 'Purchase order lines',
                'date_field': 'date_order',
            },
            'purchase_requests': {
                'model': 'purchase.request',
                'name': 'Purchase requests',
                'date_field': 'date_start',
            },
            'pending_pr': {
                'model': 'purchase.request',
                'name': 'Purchase requests pending approval',
                'extra': [('validation_status', 'in', ('waiting', 'pending'))],
            },
            'approved_pr': {
                'model': 'purchase.request',
                'name': 'Approved purchase requests',
                'extra': [('validation_status', '=', 'validated')],
                'date_field': 'date_start',
            },
            'delayed_pr_lines': {
                'model': 'purchase.request.line',
                'name': 'Delayed purchase request lines',
                'extra': [('pending_qty_to_receive', '>', 0)],
                'deadline_before_today': True,
                'deadline_field': 'date_required',
            },
            'stock_quants': {
                'model': 'stock.quant',
                'name': 'On-hand stock',
                'extra': [('location_id.usage', '=', 'internal')],
            },
            'stock_valuation': {
                'model': 'stock.valuation.layer',
                'name': 'Stock valuation',
            },
            'stock_valuation_movement': {
                'model': 'stock.valuation.layer',
                'name': 'Stock valuation movement',
                'valuation_date': True,
            },
            'pickings': {
                'model': 'stock.picking',
                'name': 'Transfers',
                'date_field': 'scheduled_date',
            },
            'receipts_done': {
                'model': 'stock.picking',
                'name': 'Completed receipts',
                'extra': [('picking_type_code', '=', 'incoming'), ('state', '=', 'done')],
                'operational_date': True,
            },
            'deliveries_done': {
                'model': 'stock.picking',
                'name': 'Completed deliveries',
                'extra': [('picking_type_code', '=', 'outgoing'), ('state', '=', 'done')],
                'operational_date': True,
            },
            'internal_done': {
                'model': 'stock.picking',
                'name': 'Completed internal transfers',
                'extra': [('picking_type_code', '=', 'internal'), ('state', '=', 'done')],
                'operational_date': True,
            },
            'pending_receipts': {
                'model': 'stock.picking',
                'name': 'Pending receipts',
                'extra': [('picking_type_code', '=', 'incoming'), ('state', 'not in', ('done', 'cancel'))],
            },
            'pending_deliveries': {
                'model': 'stock.picking',
                'name': 'Pending deliveries',
                'extra': [
                    ('picking_type_code', '=', 'outgoing'),
                    ('state', 'not in', ('done', 'cancel')),
                ],
            },
            'negative_stock': {
                'model': 'stock.quant',
                'name': 'Negative internal stock',
                'extra': [('quantity', '<', 0), ('location_id.usage', '=', 'internal')],
            },
            'gate_passes': {
                'model': 'ages.gate.pass',
                'name': 'Gate passes',
                'date_field': 'pass_date',
            },
            'waiting_gate_passes': {
                'model': 'ages.gate.pass',
                'name': 'Gate passes waiting for security',
                'extra': [('state', 'in', ('draft', 'waiting_security'))],
            },
            'overdue_rgp': {
                'model': 'ages.gate.pass',
                'name': 'Overdue returnable gate passes',
                'extra': [('return_state', '=', 'overdue')],
            },
            'material_consumption': {
                'model': 'ages.material.consumption',
                'name': 'Material consumption',
                'date_field': 'date',
            },
            'incomplete_consumption': {
                'model': 'ages.material.consumption',
                'name': 'Incomplete material consumption',
                'extra': [('state', 'in', ('draft', 'confirmed'))],
            },
            'ages_expenses': {
                'model': 'ages.expense',
                'name': 'AGES expenses',
                'date_field': 'date',
            },
            'hr_expenses': {
                'model': 'hr.expense',
                'name': 'Employee expenses',
                'date_field': 'date',
            },
            'employees': {
                'model': 'hr.employee',
                'name': 'Employees',
            },
            'active_employees': {
                'model': 'hr.employee',
                'name': 'Active employees',
                'extra': [('active', '=', True)],
            },
            'inactive_employees': {
                'model': 'hr.employee',
                'name': 'Inactive employees',
                'extra': [('active', '=', False)],
            },
            'employees_no_department': {
                'model': 'hr.employee',
                'name': 'Employees without department',
                'extra': [('active', '=', True), ('department_id', '=', False)],
            },
            'employees_no_project': {
                'model': 'hr.employee',
                'name': 'Employees without project',
                'extra': [('active', '=', True), ('project_id', '=', False)],
            },
            'new_hires': {
                'model': 'hr.employee',
                'name': 'New employee records',
                'date_field': 'create_date',
            },
            'employee_departures': {
                'model': 'hr.employee',
                'name': 'Employee departures',
                'date_field': 'departure_date',
            },
            'employee_transfers': {
                'model': 'hr.employee.project.tracking',
                'name': 'Employee project transfers',
                'date_field': 'date',
            },
            'wage_changes': {
                'model': 'hr.employee.wage.history',
                'name': 'Employee wage changes',
                'date_field': 'date',
            },
            'leave_records': {
                'model': 'hr.leave',
                'name': 'Time off',
                'date_field': 'date_from',
            },
            'payslips': {
                'model': 'hr.payslip',
                'name': 'Payslips',
                'date_field': 'date_from',
            },
            'draft_payslips': {
                'model': 'hr.payslip',
                'name': 'Draft payslips',
                'extra': [('state', 'in', ('draft', 'verify'))],
            },
            'pending_payslips': {
                'model': 'hr.payslip',
                'name': 'Pending payslips',
                'extra': [('state', 'in', ('draft', 'verify'))],
                'date_field': 'date_from',
            },
            'finalized_payslips': {
                'model': 'hr.payslip',
                'name': 'Finalized payslips',
                'extra': [('state', 'in', ('done', 'paid'))],
                'date_field': 'date_from',
            },
            'done_payslips': {
                'model': 'hr.payslip',
                'name': 'Finalized unpaid payslips',
                'extra': [('state', '=', 'done')],
                'date_field': 'date_from',
            },
            'paid_payslips': {
                'model': 'hr.payslip',
                'name': 'Paid payslips',
                'extra': [('state', '=', 'paid')],
                'date_field': 'date_from',
            },
            'payslips_missing_move': {
                'model': 'hr.payslip',
                'name': 'Finalized payslips without journal entry',
                'extra': [('state', 'in', ('done', 'paid')), ('move_id', '=', False)],
                'date_field': 'date_from',
            },
            'payslips_missing_move_all': {
                'model': 'hr.payslip',
                'name': 'Finalized payslips without journal entry',
                'extra': [('state', 'in', ('done', 'paid')), ('move_id', '=', False)],
            },
            'payslips_missing_payment': {
                'model': 'hr.payslip',
                'name': 'Paid payslips without payment move',
                'extra': [('state', '=', 'paid'), ('payment_move_id', '=', False)],
                'date_field': 'date_from',
            },
            'attendances': {
                'model': 'hr.attendance',
                'name': 'Attendances',
                'date_field': 'check_in',
            },
            'missing_checkouts': {
                'model': 'hr.attendance',
                'name': 'Attendance missing check-out',
                'extra': [('check_out', '=', False)],
                'date_field': 'check_in',
            },
            'work_entry_conflicts': {
                'model': 'hr.work.entry',
                'name': 'Conflicting work entries',
                'extra': [('state', '=', 'conflict')],
                'date_field': 'date_start',
            },
            'work_entry_conflicts_all': {
                'model': 'hr.work.entry',
                'name': 'Conflicting work entries',
                'extra': [('state', '=', 'conflict')],
            },
            'draft_work_entries': {
                'model': 'hr.work.entry',
                'name': 'Draft work entries',
                'extra': [('state', '=', 'draft')],
                'date_field': 'date_start',
            },
            'draft_work_entries_all': {
                'model': 'hr.work.entry',
                'name': 'Draft work entries',
                'extra': [('state', '=', 'draft')],
            },
            'validated_work_entries': {
                'model': 'hr.work.entry',
                'name': 'Validated work entries',
                'extra': [('state', '=', 'validated')],
                'date_field': 'date_start',
            },
            'pending_leave': {
                'model': 'hr.leave',
                'name': 'Time off awaiting approval',
                'extra': [('state', 'in', ('confirm', 'validate1'))],
            },
            'leave_payroll_blocked': {
                'model': 'hr.leave',
                'name': 'Leave blocked from current payroll',
                'extra': [('payslip_state', '=', 'blocked')],
            },
            'followup_partners': {
                'model': 'res.partner',
                'name': 'Follow-up next actions due',
                'extra': [('payment_next_action_date', '!=', False)],
                'due_action_today': True,
            },
            'portal_attendance': {
                'model': 'project.portal.attendance',
                'name': 'Portal attendance',
                'date_field': 'date',
            },
            'portal_sync_failures': {
                'model': 'project.portal.attendance',
                'name': 'Portal attendance sync failures',
                'extra': [('sync_state', '=', 'failed')],
            },
            'portal_sync_failures_period': {
                'model': 'project.portal.attendance',
                'name': 'Portal attendance sync failures',
                'extra': [('sync_state', '=', 'failed')],
                'date_field': 'date',
            },
            'sale_orders': {
                'model': 'sale.order',
                'name': 'Sales orders',
                'date_field': 'date_order',
            },
            'sale_order_lines': {
                'model': 'sale.order.line',
                'name': 'Sales order lines',
            },
            'assets_oca': {
                'model': 'account.asset',
                'name': 'Assets',
            },
            'assets_om': {
                'model': 'account.asset.asset',
                'name': 'Assets',
            },
            'asset_lines_oca': {
                'model': 'account.asset.line',
                'name': 'OCA depreciation lines',
                'date_field': 'line_date',
            },
            'asset_lines_oca_all': {
                'model': 'account.asset.line',
                'name': 'OCA depreciation lines',
            },
            'asset_lines_om': {
                'model': 'account.asset.depreciation.line',
                'name': 'OdooMates depreciation lines',
                'date_field': 'depreciation_date',
            },
            'asset_lines_om_all': {
                'model': 'account.asset.depreciation.line',
                'name': 'OdooMates depreciation lines',
            },
            'tier_reviews': {
                'model': 'tier.review',
                'name': 'Approval reviews',
            },
            'crm_leads': {
                'model': 'crm.lead',
                'name': 'CRM pipeline',
            },
            'mrp_orders': {
                'model': 'mrp.production',
                'name': 'Manufacturing orders',
            },
            'quality_checks': {
                'model': 'quality.check',
                'name': 'Quality checks',
            },
            'quality_pending': {
                'model': 'quality.check',
                'name': 'Pending quality checks',
                'extra': [('quality_state', 'not in', ('pass', 'fail'))],
            },
            'quality_failed': {
                'model': 'quality.check',
                'name': 'Failed quality checks',
                'extra': [('quality_state', '=', 'fail')],
            },
            'construction_boq': {
                'model': 'construction.boq',
                'name': 'Construction BOQ',
            },
            'construction_co': {
                'model': 'construction.change.order',
                'name': 'Construction change orders',
            },
            'construction_mr': {
                'model': 'construction.material.request',
                'name': 'Construction material requests',
            },
            'construction_log': {
                'model': 'construction.daily.log',
                'name': 'Construction daily logs',
            },
            'construction_progress': {
                'model': 'construction.progress.entry',
                'name': 'Construction progress entries',
            },
            'construction_rfi': {
                'model': 'construction.rfi',
                'name': 'Construction RFIs',
            },
            'construction_sub': {
                'model': 'construction.subcontract',
                'name': 'Construction subcontracts',
            },
            'construction_eq': {
                'model': 'construction.equipment.assignment',
                'name': 'Construction equipment assignments',
            },
            'mrp_waiting': {
                'model': 'mrp.production',
                'name': 'Manufacturing orders waiting components',
                'extra': [
                    ('state', 'not in', ('done', 'cancel')),
                    ('reservation_state', 'in', ('waiting', 'confirmed')),
                ],
            },
            'timeout_sessions': {
                'model': 'ages.user.session',
                'name': 'Inactivity timeout sessions',
                'extra': [('logout_reason', '=', 'inactivity_timeout')],
            },
            'user_sessions': {
                'model': 'ages.user.session',
                'name': 'User sessions',
            },
            'deletion_audit': {
                'model': 'ages.deletion.audit',
                'name': 'Deleted records',
                'date_field': 'create_date',
            },
            'orderpoints': {
                'model': 'stock.warehouse.orderpoint',
                'name': 'Reordering rules',
            },
            'unreconciled': {
                'model': 'account.move.line',
                'name': 'Unreconciled journal items',
                'extra': [
                    ('parent_state', '=', 'posted'),
                    ('reconciled', '=', False),
                    ('account_id.reconcile', '=', True),
                    ('amount_residual', '!=', 0),
                ],
            },
            'unpaid_ra': {
                'model': 'ages.running.bill',
                'name': 'Unpaid or partial RA invoices',
                'extra': [
                    ('state', '=', 'confirmed'),
                    ('invoice_payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
                ],
            },
            'missing_ra_invoices': {
                'model': 'ages.running.bill',
                'name': 'Confirmed RA missing an invoice',
                'extra': [
                    ('state', '=', 'confirmed'),
                    ('invoice_id', '=', False),
                ],
            },
            'overdue_receipts': {
                'model': 'stock.picking',
                'name': 'Overdue purchase receipts',
                'extra': [
                    ('picking_type_code', '=', 'incoming'),
                    ('state', 'not in', ('done', 'cancel')),
                ],
                'deadline_before_today': True,
                'deadline_field': 'scheduled_date',
            },
            'overdue_transfers': {
                'model': 'stock.picking',
                'name': 'Overdue transfers',
                'extra': [('state', 'not in', ('done', 'cancel'))],
                'deadline_before_today': True,
                'deadline_field': 'scheduled_date',
            },
            'expiring_contracts': {
                'model': 'ages.contract',
                'name': 'Contracts near close date',
                'extra': [
                    ('state', 'in', ('new', 'running')),
                    ('date_close', '!=', False),
                ],
                'expiry_horizon': True,
            },
            'mobilization': {
                'model': 'ages.mobilization.advance',
                'name': 'Mobilization advances',
            },
            'retention': {
                'model': 'ages.retention.recovery',
                'name': 'Retention recoveries',
            },
            'budgets': {
                'model': 'crossovered.budget',
                'name': 'Budgets',
            },
            'loan_installments': {
                'model': 'hr.loan.installment',
                'name': 'Loan installments',
                'date_field': 'due_date',
            },
            'overdue_loan_installments': {
                'model': 'hr.loan.installment',
                'name': 'Overdue loan installments',
                'extra': [('deduction_state', 'in', ('pending', 'partial'))],
                'deadline_before_today': True,
                'deadline_field': 'due_date',
            },
            'payslip_runs': {
                'model': 'hr.payslip.run',
                'name': 'Payslip batches',
            },
            'pending_pr_qty': {
                'model': 'purchase.request.line',
                'name': 'PR quantities pending receipt',
                'extra': [('pending_qty_to_receive', '>', 0)],
            },
            'work_entries': {
                'model': 'hr.work.entry',
                'name': 'Work entries',
            },
            'hr_contracts': {
                'model': 'hr.contract',
                'name': 'Employee contracts',
                'extra': [('state', '=', 'open')],
            },
            'expiring_hr_contracts': {
                'model': 'hr.contract',
                'name': 'Contracts nearing end',
                'extra': [('state', '=', 'open'), ('date_end', '!=', False)],
                'hr_contract_horizon': True,
            },
            'asset_transfers': {
                'model': 'asset.transfer',
                'name': 'Asset transfers awaiting action',
                'extra': [('state', 'not in', ('done', 'cancelled'))],
            },
            'purchase_commitments': {
                'model': 'purchase.order',
                'name': 'Open purchase commitments',
                'extra': [
                    ('state', 'in', ('purchase', 'done')),
                    ('invoice_status', 'in', ('no', 'to invoice')),
                ],
            },
            'pending_po_receipts': {
                'model': 'purchase.order',
                'name': 'Purchase orders pending receipt',
                'extra': [
                    ('state', 'in', ('purchase', 'done')),
                    ('receipt_status', 'in', ('pending', 'partial')),
                ],
            },
            'below_reorder': {
                'model': 'stock.warehouse.orderpoint',
                'name': 'Below-reorder products',
                'dynamic': 'below_reorder',
            },
            'missing_checkouts_all': {
                'model': 'hr.attendance',
                'name': 'Attendance missing check-out',
                'extra': [('check_out', '=', False)],
            },
            'low_stock': {
                'model': 'stock.warehouse.orderpoint',
                'name': 'Below-reorder products',
                'dynamic': 'below_reorder',
            },
        }

    @api.model
    def open_action(self, action_key, filters=None, extra_domain=None):
        spec = self._action_specs().get(action_key)
        if not spec:
            return False
        model_name = spec['model']
        if model_name == 'hr.payslip.line':
            return False
        if not self._can_read(model_name):
            return False
        caps = self._capability_map()
        if model_name in ('account.move', 'account.move.line', 'account.payment', 'account.journal') and not caps.get('account'):
            return False
        if model_name in ('hr.payslip', 'hr.payslip.run', 'hr.payslip.line', 'hr.loan.installment') and not caps.get('payroll'):
            return False
        if model_name == 'hr.leave' and not (caps.get('hr') or caps.get('payroll')):
            return False
        if model_name in (
            'hr.employee', 'hr.contract',
            'hr.employee.project.tracking', 'hr.employee.wage.history',
        ) and not caps.get('hr'):
            return False
        if model_name == 'ages.deletion.audit' and not caps.get('audit'):
            return False
        if model_name == 'ages.user.session' and not caps.get('presence'):
            return False
        if model_name in ('project.project', 'project.task') and not caps.get('project'):
            return False
        if model_name in ('purchase.order', 'purchase.order.line') and not caps.get('purchase'):
            return False
        if model_name in ('purchase.request', 'purchase.request.line') and not (
            caps.get('purchase') or caps.get('purchase_request')
        ):
            return False
        if model_name.startswith('stock.') and not caps.get('stock'):
            return False
        scope = self._normalize_filters(filters)
        domain = self._scope_domain(model_name, scope)
        extra = list(spec.get('extra') or [])
        from odoo import fields as odoo_fields
        today = odoo_fields.Date.context_today(self)
        if spec.get('dynamic') == 'below_reorder':
            data = self._below_reorder_data(scope)
            ids = [row.get('res_id') for row in data.get('rows') or [] if row.get('res_id')]
            extra.append(('id', 'in', ids or [0]))
        grace = max(self._config_int('ages_enterprise_dashboard.overdue_grace_days', 0), 0)
        overdue_cutoff = today - timedelta(days=grace)
        cleaned_extra = []
        for leaf in extra:
            if (
                isinstance(leaf, (list, tuple))
                and len(leaf) == 3
                and not self._field_path_exists(model_name, leaf[0])
            ):
                return False
            if spec.get('due_before_today') and len(leaf) == 3 and leaf[0] == 'invoice_date_due' and leaf[2] is False:
                cleaned_extra.append(('invoice_date_due', '<', overdue_cutoff))
            elif spec.get('deadline_before_today') and len(leaf) == 3 and leaf[0] == 'date_deadline' and leaf[2] is False:
                cleaned_extra.append(('date_deadline', '<', today))
            else:
                cleaned_extra.append(leaf)
        deadline_field = spec.get('deadline_field')
        if spec.get('deadline_before_today') and deadline_field:
            if not self._field_path_exists(model_name, deadline_field):
                return False
            cleaned_extra.append((deadline_field, '<', today))
        if spec.get('expiry_horizon'):
            if not self._has_field(model_name, 'date_close'):
                return False
            expiry_days = max(self._config_int('ages_enterprise_dashboard.contract_expiry_days', 30), 0)
            horizon_base = scope.get('date_to') or today
            cleaned_extra.append(('date_close', '<=', horizon_base + timedelta(days=expiry_days)))
        if spec.get('hr_contract_horizon'):
            if not self._has_field(model_name, 'date_end'):
                return False
            expiry_days = max(self._config_int('ages_enterprise_dashboard.hr_contract_expiry_days', 30), 0)
            horizon_base = scope.get('date_to') or today
            cleaned_extra.append(('date_end', '<=', horizon_base + timedelta(days=expiry_days)))
        if spec.get('due_action_today'):
            if not self._has_field(model_name, 'payment_next_action_date'):
                return False
            cleaned_extra.append(('payment_next_action_date', '<=', today))
        if spec.get('operational_date'):
            operational_field = 'actual_date' if self._has_field(model_name, 'actual_date') else 'date_done'
            if not self._has_field(model_name, operational_field):
                operational_field = 'scheduled_date'
            cleaned_extra.extend(self._date_domain(
                operational_field, scope.get('date_from'), scope.get('date_to')
            ))
        if spec.get('valuation_date'):
            valuation_field = 'actual_date' if self._has_field(model_name, 'actual_date') else 'create_date'
            cleaned_extra.extend(self._typed_date_domain(
                model_name, valuation_field, scope.get('date_from'), scope.get('date_to')
            ))
        if cleaned_extra:
            domain = expression.AND([domain, cleaned_extra])
        date_field = False if spec.get('skip_date') else spec.get('date_field')
        if date_field and self._field_path_exists(model_name, date_field):
            domain = expression.AND([domain, self._typed_date_domain(
                model_name, date_field, scope.get('date_from'), scope.get('date_to')
            )])
        through_date_field = spec.get('through_date_field')
        if through_date_field and self._field_path_exists(model_name, through_date_field) and scope.get('date_to'):
            domain = expression.AND([domain, [(through_date_field, '<=', scope['date_to'])]])
        if extra_domain:
            if not isinstance(extra_domain, list):
                extra_domain = []
            safe = []
            allowed_extra_fields = {
                'id', 'partner_id', 'employee_id', 'account_id', 'journal_id',
                'product_id', 'project_id', 'ages_project_id', 'contract_id',
                'department_id', 'state', 'user_id', 'team_id', 'requested_by',
                'quality_state', 'picking_type_code', 'invoice_status',
                'receipt_status', 'move_type', 'payment_state',
                'move_id.ages_project_id', 'move_id.ages_sub_company_id',
                'analytic_distribution', 'categ_id', 'warehouse_id',
                'location_id', 'product_id.categ_id',
                'invoice_payment_state', 'validation_status',
                'ages_contract_id', 'sub_company_id', 'ages_sub_company_id',
            }
            for leaf in extra_domain:
                if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and isinstance(leaf[0], str):
                    if (
                        leaf[0] in allowed_extra_fields
                        and self._field_path_exists(model_name, leaf[0])
                        and leaf[1] in ('=', '!=', '>', '>=', '<', '<=', 'in', 'not in')
                    ):
                        safe.append(tuple(leaf))
            if safe:
                domain = expression.AND([domain, safe])
        views = spec.get('views') or [[False, 'list'], [False, 'form']]
        return {
            'type': 'ir.actions.act_window',
            'name': spec.get('name') or model_name,
            'res_model': model_name,
            'view_mode': 'list,form',
            'views': views,
            'domain': domain,
            'context': {'create': False},
            'target': 'current',
        }

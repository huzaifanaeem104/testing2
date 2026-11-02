# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAgesDeletionAudit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env['ages.deletion.audit']
        cls.partner = cls.env['res.partner'].create({
            'name': 'Deletion Audit Partner',
        })

    def setUp(self):
        super().setUp()
        self.Audit._ages_clear_area_cache()

    def _create_project(self, name, **vals):
        values = {'name': name}
        values.update(vals)
        return self.env['project.project'].with_context(ages_skip_auto_setup=True).create(values)

    def _logs(self, model_name, record_id=None):
        domain = [('model_name', '=', model_name)]
        if record_id is not None:
            domain.append(('record_id', '=', record_id))
        return self.Audit.sudo().search(domain)

    def _assert_log(self, record, area, user=None):
        log = self._logs(record._name, record.id)
        self.assertEqual(len(log), 1, 'Expected one audit row for %s,%s' % (record._name, record.id))
        self.assertEqual(log.business_module, area)
        self.assertEqual(log.record_id, record.id)
        self.assertTrue(log.record_name)
        self.assertTrue(log.deletion_date)
        self.assertTrue(log.snapshot)
        self.assertNotIn('"password"', (log.snapshot or '').lower())
        if user is None:
            user = self.env.user
        self.assertEqual(log.deleted_by_id, user)
        self.assertEqual(log.deleted_by_uid, user.id)
        self.assertTrue(log.deleted_by_name)
        self.assertFalse(record.exists())
        return log

    def test_classify_discovered_models(self):
        classify = self.Audit._ages_classify
        self.assertEqual(classify('project.project'), 'project')
        self.assertEqual(classify('project.task'), 'project')
        self.assertEqual(classify('sale.order'), 'sales')
        self.assertEqual(classify('sale.order.line'), 'sales')
        self.assertEqual(classify('purchase.order'), 'purchase')
        self.assertEqual(classify('purchase.order.line'), 'purchase')
        self.assertEqual(classify('account.move'), 'accounting')
        self.assertEqual(classify('account.move.line'), 'accounting')
        self.assertEqual(classify('account.payment'), 'accounting')
        self.assertEqual(classify('account.account'), 'accounting')
        self.assertEqual(classify('account.journal'), 'accounting')
        self.assertEqual(classify('account.analytic.account'), 'accounting')
        self.assertEqual(classify('ages.expense'), 'expense')
        self.assertEqual(classify('ages.expense.line'), 'expense')
        self.assertEqual(classify('purchase.request'), 'purchase_request')
        self.assertEqual(classify('purchase.request.line'), 'purchase_request')
        self.assertEqual(classify('stock.picking'), 'inventory')
        self.assertEqual(classify('stock.move'), 'inventory')
        self.assertEqual(classify('stock.location'), 'inventory')
        self.assertEqual(classify('hr.employee'), 'employees')
        self.assertEqual(classify('hr.department'), 'employees')
        self.assertEqual(classify('hr.attendance'), 'attendances')
        self.assertFalse(classify('ages.deletion.audit'))
        self.assertFalse(classify('ir.model'))
        self.assertFalse(classify('mail.message'))
        self.assertFalse(classify('res.partner'))
        self.assertFalse(classify('res.users'))
        if 'ages.contract' in self.env:
            self.assertEqual(classify('ages.contract'), 'project')
        if 'ages.gate.pass' in self.env:
            self.assertEqual(classify('ages.gate.pass'), 'inventory')
        if 'hr.payslip' in self.env:
            self.assertEqual(classify('hr.payslip'), 'payroll')
        if 'account.payment.detail.line' in self.env:
            self.assertEqual(classify('account.payment.detail.line'), 'accounting')
        if 'hr.work.entry' in self.env:
            self.assertEqual(classify('hr.work.entry'), 'payroll')

    def test_project_delete(self):
        project = self._create_project('Audit Project Alpha')
        record_id = project.id
        project.unlink()
        log = self._logs('project.project', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'project')
        self.assertEqual(log.record_name, 'Audit Project Alpha')
        self.assertIn('Audit Project Alpha', log.snapshot)
        self.assertEqual(log.deletion_type, 'user_initiated')
        self.assertEqual(log.deleted_by_id, self.env.user)

    def test_sales_delete(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })
        name = order.display_name
        record_id = order.id
        order.unlink()
        log = self._logs('sale.order', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'sales')
        self.assertEqual(log.record_name, name)
        self.assertIn(str(self.partner.id), log.snapshot)

    def test_purchase_delete(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
        })
        record_id = order.id
        order.button_cancel()
        order.unlink()
        log = self._logs('purchase.order', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'purchase')

    def test_purchase_request_delete(self):
        request = self.env['purchase.request'].create({
            'requested_by': self.env.uid,
        })
        record_id = request.id
        name = request.display_name
        request.unlink()
        log = self._logs('purchase.request', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'purchase_request')
        self.assertEqual(log.record_name, name)

    def test_inventory_location_delete(self):
        parent = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        vals = {
            'name': 'Audit Loc',
            'usage': 'internal',
        }
        if parent:
            vals['location_id'] = parent.id
        location = self.env['stock.location'].create(vals)
        record_id = location.id
        location.unlink()
        log = self._logs('stock.location', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'inventory')
        self.assertIn('Audit Loc', log.record_name)

    def test_employee_delete(self):
        employee = self.env['hr.employee'].create({'name': 'Audit Employee'})
        record_id = employee.id
        employee.unlink()
        log = self._logs('hr.employee', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'employees')
        self.assertEqual(log.record_name, 'Audit Employee')
        snapshot_l = (log.snapshot or '').lower()
        self.assertNotIn('private_street', snapshot_l)
        self.assertNotIn('ssnid', snapshot_l)
        self.assertNotIn('identification_id', snapshot_l)

    def test_attendance_delete(self):
        employee = self.env['hr.employee'].create({'name': 'Audit Attendee'})
        attendance = self.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': datetime(2026, 1, 15, 8, 0, 0),
            'check_out': datetime(2026, 1, 15, 17, 0, 0),
        })
        record_id = attendance.id
        attendance.unlink()
        log = self._logs('hr.attendance', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'attendances')
        self.assertIn(str(employee.id), log.snapshot)

    def test_payroll_work_entry_type_if_available(self):
        if 'hr.work.entry.type' not in self.env:
            self.skipTest('hr.work.entry.type is not installed')
        work_type = self.env['hr.work.entry.type'].create({
            'name': 'Audit WE Type',
            'code': 'AUDITWE',
        })
        record_id = work_type.id
        work_type.unlink()
        log = self._logs('hr.work.entry.type', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'payroll')

    def test_bulk_project_delete(self):
        projects = self.env['project.project']
        for idx in range(4):
            projects |= self._create_project('Bulk %s' % idx)
        ids = list(projects.ids)
        projects.unlink()
        logs = self.Audit.sudo().search([
            ('model_name', '=', 'project.project'),
            ('record_id', 'in', ids),
        ])
        self.assertEqual(len(logs), 4)
        self.assertEqual(set(logs.mapped('record_id')), set(ids))
        self.assertTrue(all(log.deletion_type == 'user_initiated' for log in logs))

    def test_failed_delete_does_not_keep_audit(self):
        request = self.env['purchase.request'].create({
            'requested_by': self.env.uid,
        })
        request.write({'state': 'approved'})
        record_id = request.id
        with self.assertRaises(UserError):
            with self.env.cr.savepoint():
                request.unlink()
        self.assertTrue(request.exists())
        self.assertFalse(self._logs('purchase.request', record_id))

    def test_audit_records_are_read_only(self):
        project = self._create_project('Lock Me')
        record_id = project.id
        project.unlink()
        log = self._logs('project.project', record_id)
        with self.assertRaises(UserError):
            log.write({'record_name': 'tampered'})
        with self.assertRaises(UserError):
            log.unlink()

    def test_ordinary_user_cannot_read_or_change_audit(self):
        project = self._create_project('Secret Delete')
        record_id = project.id
        project.unlink()
        user = new_test_user(
            self.env, login='audit_plain_user', password='password',
            groups='base.group_user',
        )
        with self.assertRaises(AccessError):
            self.Audit.with_user(user).search([
                ('model_name', '=', 'project.project'),
                ('record_id', '=', record_id),
            ])

    def test_project_manager_sees_only_project_logs(self):
        project = self._create_project('PM Project')
        project_id = project.id
        project.unlink()
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        order_id = order.id
        order.unlink()
        manager = new_test_user(
            self.env, login='audit_project_manager', password='password',
            groups='base.group_user,project.group_project_manager',
        )
        seen = self.Audit.with_user(manager).search([
            ('record_id', 'in', [project_id, order_id]),
            ('model_name', 'in', ['project.project', 'sale.order']),
        ])
        self.assertEqual(seen.mapped('model_name'), ['project.project'])

    def test_scheduled_source_from_context(self):
        project = self._create_project('Cron Delete')
        record_id = project.id
        project.with_context(cron_id=1).unlink()
        log = self._logs('project.project', record_id)
        self.assertEqual(log.deletion_source, 'scheduled')

    def test_company_retained(self):
        project = self._create_project('Company Project', company_id=self.env.company.id)
        record_id = project.id
        project.unlink()
        log = self._logs('project.project', record_id)
        self.assertEqual(log.company_id, self.env.company)
        self.assertTrue(log.company_name)

    def test_exception_exclude_and_include(self):
        model = self.env['ir.model']._get('sale.order')
        self.env['ages.deletion.audit.exception'].create({
            'model_id': model.id,
            'action': 'exclude',
        })
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        record_id = order.id
        order.unlink()
        self.assertFalse(self._logs('sale.order', record_id))

        partner_model = self.env['ir.model']._get('res.partner')
        self.env['ages.deletion.audit.exception'].create({
            'model_id': partner_model.id,
            'action': 'include',
            'business_module': 'sales',
        })
        partner = self.env['res.partner'].create({'name': 'Included Partner'})
        partner_id = partner.id
        partner.unlink()
        log = self._logs('res.partner', partner_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'sales')

    def test_custom_contract_if_installed(self):
        if 'ages.contract' not in self.env or 'ages.sub.company' not in self.env:
            self.skipTest('ages.contract is not installed')
        Sub = self.env['ages.sub.company']
        sub = Sub.search([('company_id', '=', self.env.company.id)], limit=1)
        if not sub:
            sub = Sub.create({
                'name': 'Audit Sub',
                'short_code': 'AUDT',
                'company_id': self.env.company.id,
            })
        contract = self.env['ages.contract'].create({
            'partner_id': self.partner.id,
            'sub_company_id': sub.id,
            'company_id': self.env.company.id,
        })
        record_id = contract.id
        contract.unlink()
        log = self._logs('ages.contract', record_id)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'project')

    def test_sensitive_snapshot_excludes_employee_private_fields(self):
        employee = self.env['hr.employee'].create({
            'name': 'Private Person',
            'private_email': 'secret@example.com',
            'pin': '1234',
        })
        record_id = employee.id
        employee.unlink()
        log = self._logs('hr.employee', record_id)
        snapshot = log.snapshot or ''
        self.assertNotIn('secret@example.com', snapshot)
        self.assertNotIn('1234', snapshot)

    def test_bulk_delete_performance_batch(self):
        projects = self.env['project.project']
        for idx in range(25):
            projects |= self._create_project('Perf %s' % idx)
        ids = list(projects.ids)
        projects.unlink()
        self.assertEqual(self.Audit.sudo().search_count([
            ('model_name', '=', 'project.project'),
            ('record_id', 'in', ids),
        ]), 25)


@tagged('post_install', '-at_install')
class TestAgesDeletionAuditAccounting(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env['ages.deletion.audit']

    def setUp(self):
        super().setUp()
        self.Audit._ages_clear_area_cache()

    def test_accounting_move_and_cascade_lines(self):
        journal = self.company_data['default_journal_misc']
        account = self.company_data['default_account_revenue']
        counterpart = self.company_data['default_account_expense']
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': 'Audit JE',
            'line_ids': [
                Command.create({
                    'name': 'Debit',
                    'account_id': account.id,
                    'debit': 10.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': 'Credit',
                    'account_id': counterpart.id,
                    'debit': 0.0,
                    'credit': 10.0,
                }),
            ],
        })
        move_id = move.id
        line_ids = list(move.line_ids.ids)
        self.assertTrue(line_ids)
        move.unlink()
        move_log = self.Audit.sudo().search([
            ('model_name', '=', 'account.move'),
            ('record_id', '=', move_id),
        ])
        self.assertEqual(len(move_log), 1)
        self.assertEqual(move_log.business_module, 'accounting')
        self.assertEqual(move_log.deletion_type, 'user_initiated')
        self.assertIn('Audit JE', move_log.snapshot)
        line_logs = self.Audit.sudo().search([
            ('model_name', '=', 'account.move.line'),
            ('record_id', 'in', line_ids),
        ])
        self.assertEqual(len(line_logs), len(line_ids))
        self.assertTrue(all(log.deletion_type == 'cascade' for log in line_logs))
        self.assertTrue(all(log.parent_model == 'account.move' for log in line_logs))

    def test_posted_move_failed_delete_rolls_back_audit(self):
        move = self.init_invoice('out_invoice', products=self.product_a, post=True)
        line_ids = list(move.line_ids.ids)
        self.assertTrue(line_ids)
        with self.assertRaises(UserError):
            with self.env.cr.savepoint():
                move.line_ids.unlink()
        self.assertTrue(move.exists())
        self.assertFalse(self.Audit.sudo().search([
            ('model_name', '=', 'account.move.line'),
            ('record_id', 'in', line_ids),
        ]))

    def test_expense_delete(self):
        journal = self.company_data.get('default_journal_cash') or self.company_data['default_journal_bank']
        expense = self.env['ages.expense'].create({
            'description': 'Audit Expense',
            'journal_id': journal.id,
            'date': fields.Date.today(),
        })
        record_id = expense.id
        expense.unlink()
        log = self.Audit.sudo().search([
            ('model_name', '=', 'ages.expense'),
            ('record_id', '=', record_id),
        ])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.business_module, 'expense')
        self.assertIn('Audit Expense', log.snapshot)

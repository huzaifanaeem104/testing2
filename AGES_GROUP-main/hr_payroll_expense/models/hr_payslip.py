# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
from odoo.exceptions import AccessError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    expense_sheet_ids = fields.One2many(
        'hr.expense.sheet', 'payslip_id', string='Expenses',
        help='Expenses to reimburse to the employee.',
    )
    expenses_count = fields.Integer(compute='_compute_expenses_count')

    @api.depends('expense_sheet_ids')
    def _compute_expenses_count(self):
        for payslip in self:
            payslip.expenses_count = len(payslip.expense_sheet_ids)

    @api.depends('employee_id', 'struct_id', 'date_from', 'date_to', 'salary_attachment_ids', 'expense_sheet_ids')
    def _compute_input_line_ids(self):
        super()._compute_input_line_ids()
        self._update_expense_input_line_ids(link_sheets=False)

    @api.model_create_multi
    def create(self, vals_list):
        payslips = super().create(vals_list)
        payslips.filtered(lambda slip: slip.employee_id and slip.state == 'draft')._link_expenses_to_payslip()
        return payslips

    def write(self, vals):
        res = super().write(vals)
        if 'expense_sheet_ids' in vals:
            self._update_expense_input_line_ids()
        if 'input_line_ids' in vals:
            self._unlink_sheets_when_input_removed()
        return res

    def action_payslip_cancel(self):
        res = super().action_payslip_cancel()
        self.expense_sheet_ids.payslip_id = False
        self._update_expense_input_line_ids()
        return res

    def action_payslip_draft(self):
        res = super().action_payslip_draft()
        self._link_expenses_to_payslip(clear_existing=False)
        return res

    def _get_employee_sheets_to_refund(self):
        return self.env['hr.expense.sheet'].sudo().search([
            ('employee_id', 'in', self.employee_id.ids),
            ('state', '=', 'approve'),
            ('payment_mode', '=', 'own_account'),
            ('refund_in_payslip', '=', True),
            ('payslip_id', '=', False),
        ])

    def _link_expenses_to_payslip(self, clear_existing=True):
        if not self:
            return
        if not (self.env.is_superuser() or self.env.user.has_group('ages_hr_payroll.group_hr_payroll_user')):
            raise AccessError(_(
                "You need to be a payroll officer to link an expense report to a payslip."
            ))
        sheets_by_employee = self._get_employee_sheets_to_refund().grouped('employee_id')
        for slip in self.sudo():
            if not slip.struct_id.rule_ids.filtered(lambda rule: rule.code == 'EXPENSES'):
                continue
            sheets = sheets_by_employee.get(slip.employee_id)
            if not sheets:
                continue
            if slip.expense_sheet_ids and clear_existing:
                slip.expense_sheet_ids = [Command.set(sheets.ids)]
            else:
                slip.expense_sheet_ids = [Command.link(sheet.id) for sheet in sheets]

    def _update_expense_input_line_ids(self, link_sheets=True):
        expense_type = self.env.ref('hr_payroll_expense.expense_other_input', raise_if_not_found=False)
        if not expense_type:
            return
        sheets_by_employee = self._get_employee_sheets_to_refund().grouped('employee_id') if not link_sheets else {}
        for slip in self.sudo():
            if not slip.struct_id.rule_ids.filtered(lambda rule: rule.code == 'EXPENSES'):
                continue
            sheets = slip.expense_sheet_ids
            if not sheets and not link_sheets:
                sheets = sheets_by_employee.get(slip.employee_id, self.env['hr.expense.sheet'])
            total = sum(sheets.mapped('total_amount'))
            lines_to_remove = slip.input_line_ids.filtered(lambda line: line.input_type_id == expense_type)
            commands = [Command.delete(line.id) for line in lines_to_remove]
            if total:
                commands.append(Command.create({
                    'name': expense_type.name,
                    'amount': total,
                    'input_type_id': expense_type.id,
                }))
            if commands:
                slip.input_line_ids = commands

    def _unlink_sheets_when_input_removed(self):
        expense_type = self.env.ref('hr_payroll_expense.expense_other_input', raise_if_not_found=False)
        if not expense_type:
            return
        for slip in self.sudo():
            if not slip.input_line_ids.filtered(lambda line: line.input_type_id == expense_type):
                slip.expense_sheet_ids.payslip_id = False

    def action_open_expenses(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Reimbursed Expenses'),
            'res_model': 'hr.expense.sheet',
        }
        if len(self.expense_sheet_ids) > 1:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.expense_sheet_ids.ids)],
            })
        else:
            action.update({
                'view_mode': 'form',
                'res_id': self.expense_sheet_ids.id,
            })
        return action

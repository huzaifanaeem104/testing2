# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    refund_in_payslip = fields.Boolean(
        string='Reimburse In Next Payslip',
        groups='hr_expense.group_hr_expense_team_approver,account.group_account_invoice,ages_hr_payroll.group_hr_payroll_user',
    )
    payslip_id = fields.Many2one('hr.payslip', string='Payslip', readonly=True, copy=False)

    def _compute_is_editable(self):
        super()._compute_is_editable()
        for sheet in self:
            sheet.is_editable = sheet.is_editable and not sheet.payslip_id

    def action_reset_expense_sheets(self):
        if any(slip.state in ('done', 'paid') for slip in self.payslip_id):
            raise UserError(_(
                "You cannot remove an expense from a payslip that has already been validated.\n"
                "Expenses can only be removed from draft or canceled payslips."
            ))
        self.sudo().action_remove_from_payslip()
        return super().action_reset_expense_sheets()

    def action_report_in_next_payslip(self):
        if not self:
            raise UserError(_("There are no valid expense reports selected."))
        if self.filtered(lambda sheet: sheet.state != 'approve' or sheet.payment_mode != 'own_account'):
            raise UserError(_(
                "Only approved expense reports that were paid by an employee can be reimbursed in a payslip."
            ))
        if any(self.account_move_ids.filtered(lambda move: move.state != 'draft')):
            raise UserError(_(
                "The accounting entries linked to this expense report do not allow reimbursement through a payslip."
            ))
        if not self.env['hr.salary.rule'].sudo().search([('code', '=', 'EXPENSES')], limit=1):
            raise UserError(_(
                "Configure a salary rule with the code EXPENSES on the relevant salary structures."
            ))
        to_report = self.filtered(lambda sheet: not sheet.refund_in_payslip)
        to_report.refund_in_payslip = True
        for record in to_report:
            record.message_post(
                body=_('Expense report "%(name)s" will be added to the next payslip.', name=record.name),
                partner_ids=record.employee_id.user_id.partner_id.ids,
            )

    def action_remove_from_payslip(self):
        valid_sheets = self.filtered(
            lambda sheet: not sheet.payslip_id or sheet.payslip_id.state in ('draft', 'verify', 'cancel')
        )
        if not valid_sheets:
            raise UserError(_(
                "You cannot remove an expense from a payslip that has already been validated.\n"
                "Expenses can only be removed from draft or canceled payslips."
            ))
        previous_payslips = valid_sheets.payslip_id
        sheets_to_edit = valid_sheets.filtered(lambda sheet: sheet.payslip_id or sheet.refund_in_payslip)
        for sheet in sheets_to_edit:
            sheet.message_post(
                body=_('Expense report "%(name)s" was removed from the next payslip.', name=sheet.name),
                partner_ids=sheet.employee_id.user_id.partner_id.ids,
            )
        sheets_to_edit.write({'refund_in_payslip': False, 'payslip_id': False})
        if previous_payslips:
            previous_payslips._update_expense_input_line_ids()

    def action_open_payslip(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslip'),
            'res_model': 'hr.payslip',
            'view_mode': 'form',
            'res_id': self.payslip_id.id,
        }

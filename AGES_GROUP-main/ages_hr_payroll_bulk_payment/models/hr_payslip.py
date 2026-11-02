# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        compute='_compute_project_and_analytic',
        store=True,
        readonly=True,
        help="Current project of the employee."
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        compute='_compute_project_and_analytic',
        store=True,
        readonly=True,
        help="Analytic account linked to the employee's project."
    )
    payment_move_id = fields.Many2one(
        'account.move',
        string='Payment Entry',
        readonly=True,
        copy=False,
        help="Journal entry generated for paying this payslip."
    )

    @api.depends('employee_id', 'employee_id.project_id')
    def _compute_project_and_analytic(self):
        for slip in self:
            slip.project_id = slip.employee_id.project_id if slip.employee_id else False
            analytic = False
            if slip.project_id:
                if hasattr(slip.project_id, 'account_id') and slip.project_id.account_id:
                    analytic = slip.project_id.account_id
                elif hasattr(slip.project_id, 'analytic_account_id') and slip.project_id.analytic_account_id:
                    analytic = slip.project_id.analytic_account_id
            slip.analytic_account_id = analytic

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        res = super()._prepare_line_values(line, account_id, date, debit, credit)
        if self.analytic_account_id and not res.get('analytic_distribution'):
            res['analytic_distribution'] = {self.analytic_account_id.id: 100}
        return res

    def action_payslip_done(self):
        res = super().action_payslip_done()
        for slip in self:
            if slip.move_id and slip.move_id.state == 'draft':
                slip.move_id.action_post()
        return res

    def _ages_reset_cancel_move(self, move):
        """Draft then cancel/unlink a linked journal entry."""
        if not move:
            return
        move = move.exists()
        if not move:
            return
        try:
            if move.state == 'posted':
                move.line_ids.remove_move_reconcile()
                move.button_draft()
            if move.exists() and move.state == 'draft':
                if hasattr(move, 'button_cancel'):
                    move.button_cancel()
                else:
                    move.unlink()
        except Exception:
            if move.exists() and move.state == 'posted':
                move.button_draft()
            if move.exists() and move.state == 'draft':
                move.unlink()

    def action_payslip_unpaid(self):
        """Paid → Done: reset/cancel payment journal entry and clear payment link."""
        paid = self.filtered(lambda s: s.state == 'paid')
        if len(paid) != len(self):
            raise UserError(_('Unpaid is only allowed for payslips in Paid state.'))

        for slip in paid:
            self._ages_reset_cancel_move(slip.payment_move_id)
            slip.payment_move_id = False

        return super().action_payslip_unpaid()

    def action_payslip_cancel(self):
        """Cancel payslip and reset/cancel expense + payment journal entries."""
        for slip in self:
            self._ages_reset_cancel_move(slip.payment_move_id)
            slip.payment_move_id = False
            if slip.move_id:
                move = slip.move_id
                self._ages_reset_cancel_move(move)
                if not move.exists():
                    slip.move_id = False
                elif move.state == 'draft':
                    move.unlink()
                    slip.move_id = False
        return super().action_payslip_cancel()

    def action_payslip_draft(self):
        """Cancelled / Verify → Draft. Clear leftover accounting links."""
        for slip in self.filtered(lambda s: s.state == 'cancel'):
            if slip.payment_move_id:
                self._ages_reset_cancel_move(slip.payment_move_id)
                slip.payment_move_id = False
            if slip.move_id:
                move = slip.move_id
                self._ages_reset_cancel_move(move)
                if not move.exists() or move.state in ('draft', 'cancel'):
                    if move.exists() and move.state == 'draft':
                        move.unlink()
                    slip.move_id = False
        return super().action_payslip_draft()

    def action_view_expense_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No expense journal entry linked to this payslip."))
        return {
            'name': _('Expense Journal Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': self.move_id.id,
        }

    def action_view_payment_move(self):
        self.ensure_one()
        if not self.payment_move_id:
            raise UserError(_("No payment journal entry linked to this payslip."))
        return {
            'name': _('Payment Journal Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': self.payment_move_id.id,
        }

    def action_open_bulk_payment_wizard(self):
        """Open payment wizard for selected payslips (list Action or form button)."""
        active_ids = self.env.context.get('active_ids') or self.ids
        payslips = self.browse(active_ids).exists()
        if not payslips and self:
            payslips = self

        if not payslips:
            raise UserError(_("Please select at least one payslip to register payment."))

        invalid_state = payslips.filtered(lambda p: p.state != 'done')
        if invalid_state:
            raise UserError(_(
                "Payment can only be registered for payslips in 'Done' state. "
                "Unmatched payslips: %s"
            ) % ', '.join(invalid_state.mapped('name') or invalid_state.mapped('number')))

        unposted_move = payslips.filtered(lambda p: not p.move_id or p.move_id.state != 'posted')
        if unposted_move:
            raise UserError(_(
                "Expense Journal Entry must be posted before registering payment. "
                "Unposted payslips: %s"
            ) % ', '.join(unposted_move.mapped('name') or unposted_move.mapped('number')))

        already_paid = payslips.filtered(lambda p: p.payment_move_id or p.state == 'paid')
        if already_paid:
            raise UserError(_(
                "The following payslips already have a payment entry linked: %s"
            ) % ', '.join(already_paid.mapped('name') or already_paid.mapped('number')))

        lines_vals = []
        for p in payslips:
            net_line = p.line_ids.filtered(lambda l: l.code == 'NET')
            amount = net_line[:1].total if net_line else (getattr(p, 'net_wage', 0.0) or 0.0)
            partner = (
                p.employee_id.work_contact_id
                or p.employee_id.user_id.partner_id
                or getattr(p.employee_id, 'address_home_id', False)
            )

            acc_id = False
            if p.move_id:
                payable_lines = p.move_id.line_ids.filtered(
                    lambda l: l.credit > 0 and (
                        l.account_id.account_type in ('liability_payable', 'liability_current')
                        or (p.journal_id and l.account_id == p.journal_id.default_account_id)
                    )
                )
                if payable_lines:
                    acc_id = payable_lines[0].account_id.id
            if not acc_id and p.journal_id and p.journal_id.default_account_id:
                acc_id = p.journal_id.default_account_id.id
            if not acc_id:
                raise UserError(_(
                    "No payable account found on expense journal entry for payslip %s. "
                    "Please check the payslip accounting configuration."
                ) % (p.name or p.number or p.display_name))

            lines_vals.append((0, 0, {
                'payslip_id': p.id,
                'employee_id': p.employee_id.id,
                'partner_id': partner.id if partner else False,
                'account_id': acc_id,
                'amount': amount,
            }))

        company = payslips.mapped('company_id')[:1] or self.env.company
        default_journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', company.id),
        ], limit=1)
        if not default_journal:
            raise UserError(_(
                "No Bank/Cash journal found for company %s. "
                "Please create one before registering payment."
            ) % company.display_name)

        wizard = self.env['hr.payslip.bulk.payment.wizard'].create({
            'company_id': company.id,
            'payment_journal_id': default_journal.id,
            'line_ids': lines_vals,
        })

        title = _('Register Payment') if len(payslips) == 1 else _('Bulk Payment')
        return {
            'name': title,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.bulk.payment.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': wizard.id,
            'target': 'new',
        }

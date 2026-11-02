# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipBulkPaymentWizard(models.TransientModel):
    _name = 'hr.payslip.bulk.payment.wizard'
    _description = 'Payslip Bulk Payment Wizard'

    payment_journal_id = fields.Many2one(
        'account.journal',
        string='Payment Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        required=True,
        default=lambda self: self._default_payment_journal_id(),
    )
    payment_date = fields.Date(
        string='Payment Date',
        default=fields.Date.today,
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        currency_field='currency_id',
        store=True
    )
    line_ids = fields.One2many(
        'hr.payslip.bulk.payment.wizard.line',
        'wizard_id',
        string='Payslips to Pay'
    )

    @api.model
    def _default_payment_journal_id(self):
        return self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for wizard in self:
            wizard.total_amount = sum(line.amount for line in wizard.line_ids)

    def action_register_payment(self):
        self.ensure_one()
        if not self.payment_journal_id:
            raise UserError(_("Please select a Payment Journal."))
        if not self.line_ids:
            raise UserError(_("No payslips selected for payment."))

        cash_bank_account = self.payment_journal_id.default_account_id
        if not cash_bank_account:
            raise UserError(_("The selected Payment Journal '%s' does not have a Default Account configured.") % self.payment_journal_id.name)

        for line in self.line_ids:
            payslip = line.payslip_id
            if payslip.state == 'paid' or payslip.payment_move_id:
                raise UserError(_("Payslip %s is already paid or linked to a payment entry.") % payslip.name)

            partner = line.partner_id
            payable_account = line.account_id or cash_bank_account
            amount = line.amount

            analytic_dist = False
            if payslip.analytic_account_id:
                analytic_dist = {payslip.analytic_account_id.id: 100}

            move_vals = {
                'journal_id': self.payment_journal_id.id,
                'date': self.payment_date,
                'ref': _('Salary Payment: %s') % payslip.name,
                'move_type': 'entry',
                'line_ids': [
                    (0, 0, {
                        'name': _('Salary Payment - %s') % payslip.employee_id.name,
                        'partner_id': partner.id if partner else False,
                        'account_id': payable_account.id,
                        'debit': amount,
                        'credit': 0.0,
                        'analytic_distribution': analytic_dist,
                    }),
                    (0, 0, {
                        'name': _('Salary Payment - %s') % payslip.employee_id.name,
                        'partner_id': partner.id if partner else False,
                        'account_id': cash_bank_account.id,
                        'debit': 0.0,
                        'credit': amount,
                        'analytic_distribution': analytic_dist,
                    }),
                ]
            }

            payment_move = self.env['account.move'].create(move_vals)
            payment_move.action_post()

            payslip.write({
                'payment_move_id': payment_move.id,
                'state': 'paid',
            })

        return {'type': 'ir.actions.act_window_close'}


class HrPayslipBulkPaymentWizardLine(models.TransientModel):
    _name = 'hr.payslip.bulk.payment.wizard.line'
    _description = 'Payslip Bulk Payment Wizard Line'

    wizard_id = fields.Many2one(
        'hr.payslip.bulk.payment.wizard',
        string='Wizard',
        ondelete='cascade'
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        required=True,
        readonly=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        readonly=True
    )
    account_id = fields.Many2one(
        'account.account',
        string='Payable Account',
        required=True
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='wizard_id.currency_id',
        readonly=True
    )

# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    ages_expense_ids = fields.One2many(
        'ages.expense',
        'payment_id',
        string='Expenses',
    )
    ages_expense_id = fields.Many2one(
        'ages.expense',
        string='Expense',
        compute='_compute_ages_expense_id',
        search='_search_ages_expense_id',
    )

    @api.depends('ages_expense_ids')
    def _compute_ages_expense_id(self):
        for payment in self:
            payment.ages_expense_id = payment.ages_expense_ids[:1]

    def _search_ages_expense_id(self, operator, value):
        return [('ages_expense_ids', operator, value)]

    def action_open_ages_expense(self):
        self.ensure_one()
        expense = self.ages_expense_id
        if not expense:
            raise UserError(_('No expense is linked to this payment.'))
        return expense._ages_open_form()

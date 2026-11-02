# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    ages_expense_id = fields.Many2one(
        'ages.expense',
        string='Expense',
        compute='_compute_ages_expense_id',
        search='_search_ages_expense_id',
    )

    @api.depends('origin_payment_id', 'origin_payment_id.ages_expense_ids')
    def _compute_ages_expense_id(self):
        Expense = self.env['ages.expense']
        missing = self.browse()
        for move in self:
            expense = move.origin_payment_id.ages_expense_ids[:1]
            if expense:
                move.ages_expense_id = expense
            else:
                missing |= move
                move.ages_expense_id = False
        if missing:
            expenses = Expense.search([('payment_id.move_id', 'in', missing.ids)])
            by_move = {expense.payment_id.move_id.id: expense for expense in expenses}
            for move in missing:
                move.ages_expense_id = by_move.get(move.id, False)

    def _search_ages_expense_id(self, operator, value):
        return [('origin_payment_id.ages_expense_ids', operator, value)]

    def action_open_ages_expense(self):
        self.ensure_one()
        expense = self.ages_expense_id
        if not expense:
            raise UserError(_('No expense is linked to this journal entry.'))
        return expense._ages_open_form()

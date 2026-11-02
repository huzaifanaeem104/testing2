# -*- coding: utf-8 -*-
from odoo import fields, models


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    account_debit = fields.Many2one('account.account', string='Debit Account', company_dependent=True)
    account_credit = fields.Many2one('account.account', string='Credit Account', company_dependent=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', company_dependent=True)
    not_computed_in_net = fields.Boolean(string="Not computed in net accountancy")
    split_move_lines = fields.Boolean(help="If set, use the payslip line name on journal items.")

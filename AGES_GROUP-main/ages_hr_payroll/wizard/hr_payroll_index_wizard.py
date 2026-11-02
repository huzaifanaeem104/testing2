# -*- coding: utf-8 -*-
from odoo import fields, models, _


class HrPayrollIndex(models.TransientModel):
    _name = 'hr.payroll.index'
    _description = 'Index contracts wages'

    percentage = fields.Float(string='Percentage (%)', required=True)
    description = fields.Char()
    contract_ids = fields.Many2many('hr.contract', string='Contracts', required=True)

    def action_confirm(self):
        self.ensure_one()
        for contract in self.contract_ids:
            if contract.wage_type == 'hourly':
                contract.hourly_wage = contract.hourly_wage * (1 + self.percentage / 100.0)
            else:
                contract.wage = contract.wage * (1 + self.percentage / 100.0)
            if self.description:
                contract.message_post(body=_('Wage indexed by %(pct)s%%: %(desc)s',
                                             pct=self.percentage, desc=self.description))
        return {'type': 'ir.actions.act_window_close'}

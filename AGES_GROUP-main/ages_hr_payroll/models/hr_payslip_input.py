# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayslipInput(models.Model):
    _name = 'hr.payslip.input'
    _description = 'Payslip Input'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description')
    payslip_id = fields.Many2one('hr.payslip', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, default=10)
    input_type_id = fields.Many2one('hr.payslip.input.type', string='Type', required=True)
    code = fields.Char(related='input_type_id.code', store=True)
    amount = fields.Float(string='Amount / Quantity')
    contract_id = fields.Many2one(related='payslip_id.contract_id')

    @api.onchange('input_type_id')
    def _onchange_input_type_id(self):
        if self.input_type_id:
            self.name = self.input_type_id.name

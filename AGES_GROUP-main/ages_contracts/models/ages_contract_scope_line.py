# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesContractScopeLine(models.Model):
    _name = 'ages.contract.scope.line'
    _description = 'Contract Scope Breakdown Line'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sr. #', default=10)
    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string='Description/Project Name',
        required=True,
    )
    amount_before_rebate = fields.Float(
        string='Before Rebate',
        digits=(16, 2),
        default=0.0,
        help='This scope item before rebate. All Before Rebate lines add up to Total Contract Value.\n'
             'Formula: typed amount.',
    )
    rebate_percent = fields.Float(
        string='%Age Rebate',
        related='contract_id.rebate_percent',
        store=True,
        readonly=True,
        digits=(16, 3),
        help='Same rebate % as the contract header. Changing contract Rebate % updates every line.\n'
             'Formula: Contract Rebate %.',
    )
    amount_after_rebate = fields.Float(
        string='After Rebate',
        compute='_compute_amount_after_rebate',
        store=True,
        readonly=False,
        digits=(16, 2),
        help='This scope item after rebate. All After Rebate lines add up to Contract-Ex. Rebate.\n'
             'Formula: Before Rebate − (Before Rebate × Rebate % / 100).',
    )
    currency_id = fields.Many2one(
        related='contract_id.currency_id',
        store=True,
        readonly=True,
    )

    @api.depends('amount_before_rebate', 'rebate_percent')
    def _compute_amount_after_rebate(self):
        for line in self:
            rebate = (line.amount_before_rebate or 0.0) * (line.rebate_percent or 0.0) / 100.0
            line.amount_after_rebate = (line.amount_before_rebate or 0.0) - rebate

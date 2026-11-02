# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesContractMaterialLine(models.Model):
    _name = 'ages.contract.material.line'
    _description = 'Contract Recovery Material Line'
    _order = 'id'

    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        index=True,
    )
    material = fields.Char(string='Material', required=True)
    quantity = fields.Float(
        string='Quantity',
        digits=(16, 2),
        default=1.0,
        help='Total quantity of this material on the contract. Running bills recover against this qty.',
    )
    uom_id = fields.Many2one(
        comodel_name='ages.secondary.uom',
        string='UOM',
        help='Unit of measure for this material (bags, kg, …).',
    )
    rate = fields.Float(
        string='Rate',
        digits=(16, 2),
        default=0.0,
        help='Rate per unit. Copied onto running-bill material lines.\n'
             'Formula: Amount = Quantity × Rate.',
    )
    amount = fields.Float(
        string='Amount',
        compute='_compute_amount',
        store=True,
        digits=(16, 2),
        help='Recovery value of this material. All line amounts add up to Material Recovery on the contract.\n'
             'Formula: Quantity × Rate.',
    )
    company_id = fields.Many2one(
        related='contract_id.company_id',
        store=True,
        readonly=True,
    )

    @api.depends('quantity', 'rate')
    def _compute_amount(self):
        for line in self:
            line.amount = (line.quantity or 0.0) * (line.rate or 0.0)

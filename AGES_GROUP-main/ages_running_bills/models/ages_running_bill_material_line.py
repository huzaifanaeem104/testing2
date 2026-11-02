# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesRunningBillMaterialLine(models.Model):
    _name = 'ages.running.bill.material.line'
    _description = 'Running Bill Recovery Material Line'
    _order = 'id'

    running_bill_id = fields.Many2one(
        comodel_name='ages.running.bill',
        string='Running Bill',
        required=True,
        ondelete='cascade',
        index=True,
    )
    contract_line_id = fields.Many2one(
        comodel_name='ages.contract.material.line',
        string='Contract Material Line',
        ondelete='set null',
        index=True,
        copy=False,
    )
    material = fields.Char(string='Material', required=True)
    quantity = fields.Float(
        string='Quantity',
        digits=(16, 2),
        default=1.0,
        help='Quantity recovered on this bill.\n'
             'Formula: typed qty. Remaining column shows This Bill / Contract Qty.',
    )
    contract_quantity = fields.Float(
        related='contract_line_id.quantity',
        string='Contract Qty',
        digits=(16, 2),
        readonly=True,
        help='Total quantity of this material on the contract.\n'
             'Formula: Contract Recovery Material quantity.',
    )
    quantity_display = fields.Char(
        string='Quantity',
        compute='_compute_quantity_display',
        help='How much of the contract quantity is recovered on this bill.\n'
             'Formula: This Bill Qty / Contract Qty.',
    )
    uom_id = fields.Many2one(
        comodel_name='ages.secondary.uom',
        string='UOM',
        help='Unit of measure for this material (bags, kg, …).',
    )
    rate = fields.Monetary(
        string='Rate',
        currency_field='currency_id',
        default=0.0,
        help='Rate per unit, copied from the contract material line.\n'
             'Formula: Amount = Quantity × Rate.',
    )
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id',
        help='Recovery value of this material. All line amounts add up to Material Recovery on the bill.\n'
             'Formula: Quantity × Rate.',
    )
    currency_id = fields.Many2one(
        related='running_bill_id.currency_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related='running_bill_id.company_id',
        store=True,
        readonly=True,
    )

    def _ages_format_qty(self, amount):
        amount = amount or 0.0
        if abs(amount - round(amount)) < 0.005:
            return '%d' % int(round(amount))
        return '%.2f' % amount

    @api.depends('quantity', 'contract_quantity', 'contract_line_id.quantity',
                 'material', 'uom_id', 'running_bill_id.contract_id.material_line_ids.quantity')
    def _compute_quantity_display(self):
        for line in self:
            contract_qty = line.contract_quantity or 0.0
            if not contract_qty and line.running_bill_id.contract_id:
                match = line.running_bill_id.contract_id.material_line_ids.filtered(
                    lambda contract_line: contract_line.material == line.material
                    and contract_line.uom_id == line.uom_id
                )[:1]
                contract_qty = match.quantity or 0.0
            if contract_qty:
                line.quantity_display = '%s/%s' % (
                    line._ages_format_qty(line.quantity),
                    line._ages_format_qty(contract_qty),
                )
            else:
                line.quantity_display = line._ages_format_qty(line.quantity)

    @api.depends('quantity', 'rate')
    def _compute_amount(self):
        for line in self:
            line.amount = (line.quantity or 0.0) * (line.rate or 0.0)

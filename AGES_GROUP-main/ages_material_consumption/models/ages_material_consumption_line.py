# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesMaterialConsumptionLine(models.Model):
    _name = 'ages.material.consumption.line'
    _description = 'Material Consumption Line'
    _order = 'id'

    consumption_id = fields.Many2one(
        comodel_name='ages.material.consumption',
        string='Material Consumption',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='consumption_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='consumption_id.currency_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
        domain="[('is_storable', '=', True)]",
        context={'default_is_storable': True},
    )
    product_uom_category_id = fields.Many2one(
        related='product_id.uom_id.category_id',
        readonly=True,
    )
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='UOM',
        required=True,
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    available_qty = fields.Float(
        string='Available',
        compute='_compute_available_qty',
        digits='Product Unit of Measure',
    )
    quantity = fields.Float(
        string='Quantity to Consume',
        digits='Product Unit of Measure',
        default=1.0,
        required=True,
    )
    qty_returned = fields.Float(
        string='Quantity Returned',
        digits='Product Unit of Measure',
        default=0.0,
        copy=False,
        readonly=True,
    )
    qty_remaining = fields.Float(
        string='Remaining',
        compute='_compute_qty_remaining',
        digits='Product Unit of Measure',
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        compute='_compute_unit_cost',
        store=True,
        digits='Product Price',
    )
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id',
    )

    @api.depends('quantity', 'qty_returned')
    def _compute_qty_remaining(self):
        for line in self:
            line.qty_remaining = (line.quantity or 0.0) - (line.qty_returned or 0.0)

    @api.depends(
        'product_id',
        'uom_id',
        'consumption_id.source_location_id',
        'consumption_id.company_id',
    )
    def _compute_available_qty(self):
        Quant = self.env['stock.quant']
        for line in self:
            if not line.product_id or not line.consumption_id.source_location_id:
                line.available_qty = 0.0
                continue
            qty = Quant._get_available_quantity(
                line.product_id,
                line.consumption_id.source_location_id,
            )
            # Convert from product UoM to line UoM when needed
            if line.uom_id and line.uom_id != line.product_id.uom_id:
                qty = line.product_id.uom_id._compute_quantity(
                    qty, line.uom_id, rounding_method='HALF-UP',
                )
            line.available_qty = qty

    @api.depends('product_id', 'company_id')
    def _compute_unit_cost(self):
        for line in self:
            product = line.product_id.with_company(line.company_id or self.env.company)
            line.unit_cost = product.standard_price if product else 0.0

    @api.depends('quantity', 'unit_cost')
    def _compute_amount(self):
        for line in self:
            line.amount = (line.quantity or 0.0) * (line.unit_cost or 0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id

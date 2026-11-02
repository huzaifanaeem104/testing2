# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesGatePassLine(models.Model):
    _name = 'ages.gate.pass.line'
    _description = 'Gate Pass Line'
    _order = 'id'

    gate_pass_id = fields.Many2one(
        comodel_name='ages.gate.pass',
        string='Gate Pass',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='gate_pass_id.company_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        check_company=True,
    )
    other_item = fields.Char(string='Other Item')
    name = fields.Char(string='Description')
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit',
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        default=1.0,
        required=True,
    )
    confirm_qty = fields.Float(
        string='Confirm Quantity',
        digits='Product Unit of Measure',
        default=1.0,
    )
    remarks = fields.Char(string='Remarks')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        self.name = self.product_id.display_name
        self.uom_id = self.product_id.uom_id

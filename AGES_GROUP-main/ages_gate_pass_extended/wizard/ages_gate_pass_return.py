# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class AgesGatePassReturn(models.TransientModel):
    _name = 'ages.gate.pass.return'
    _description = 'Return Items Against a Returnable Gate Pass (RGP)'

    rgp_id = fields.Many2one(
        comodel_name='ages.gate.pass',
        string='Returnable Gate Pass',
        required=True,
        domain=[('gate_type', '=', 'rgp')],
    )
    line_ids = fields.One2many(
        comodel_name='ages.gate.pass.return.line',
        inverse_name='wizard_id',
        string='Items to Return',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        rgp_id = res.get('rgp_id') or self.env.context.get('default_rgp_id')
        if rgp_id and 'line_ids' in fields_list:
            rgp = self.env['ages.gate.pass'].browse(rgp_id)
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            lines = []
            for line in rgp.line_ids.filtered('product_id'):
                remaining = line.confirm_qty - line.qty_returned
                if float_compare(remaining, 0.0, precision_digits=precision) <= 0:
                    continue
                lines.append((0, 0, {
                    'rgp_line_id': line.id,
                    'product_id': line.product_id.id,
                    'uom_id': line.uom_id.id,
                    'qty_remaining': remaining,
                    'qty_to_return': remaining,
                }))
            res['line_ids'] = lines
        return res

    def action_create_return(self):
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        selected = self.line_ids.filtered(
            lambda l: float_compare(l.qty_to_return, 0.0, precision_digits=precision) > 0
        )
        if not selected:
            raise UserError(_('Enter a quantity to return for at least one item.'))
        for line in selected:
            if float_compare(line.qty_to_return, line.qty_remaining, precision_digits=precision) > 0:
                raise UserError(_(
                    'Quantity to return for %(product)s (%(qty)s) exceeds the '
                    'remaining quantity (%(remaining)s).',
                    product=line.product_id.display_name,
                    qty=line.qty_to_return,
                    remaining=line.qty_remaining,
                ))

        rgp = self.rgp_id
        new_lines = [(0, 0, {
            'product_id': line.product_id.id,
            'name': line.product_id.display_name,
            'uom_id': line.uom_id.id,
            'quantity': line.qty_to_return,
            'confirm_qty': line.qty_to_return,
        }) for line in selected]

        gate_pass = self.env['ages.gate.pass'].create({
            'gate_type': 'in',
            'partner_id': rgp.partner_id.id,
            'company_id': rgp.company_id.id,
            'warehouse_id': rgp.warehouse_id.id,
            'project_id': rgp.project_id.id,
            'analytic_account_id': rgp.analytic_account_id.id,
            'sub_company_id': rgp.sub_company_id.id,
            'source_rgp_id': rgp.id,
            'pass_date': fields.Datetime.now(),
            'line_ids': new_lines,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Gate Pass'),
            'res_model': 'ages.gate.pass',
            'res_id': gate_pass.id,
            'view_mode': 'form',
            'target': 'current',
        }


class AgesGatePassReturnLine(models.TransientModel):
    _name = 'ages.gate.pass.return.line'
    _description = 'Return Gate Pass Wizard Line'

    wizard_id = fields.Many2one(
        comodel_name='ages.gate.pass.return', required=True, ondelete='cascade',
    )
    rgp_line_id = fields.Many2one(comodel_name='ages.gate.pass.line', string='Original Line')
    product_id = fields.Many2one(comodel_name='product.product', string='Item', readonly=True)
    uom_id = fields.Many2one(comodel_name='uom.uom', string='UoM', readonly=True)
    qty_remaining = fields.Float(
        string='Not Yet Returned', digits='Product Unit of Measure', readonly=True,
    )
    qty_to_return = fields.Float(
        string='Return Now', digits='Product Unit of Measure',
    )

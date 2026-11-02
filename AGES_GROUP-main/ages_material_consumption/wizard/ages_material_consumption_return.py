# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class AgesMaterialConsumptionReturn(models.TransientModel):
    _name = 'ages.material.consumption.return'
    _description = 'Material Consumption Return'

    consumption_id = fields.Many2one(
        comodel_name='ages.material.consumption',
        string='Material Consumption',
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(related='consumption_id.company_id', readonly=True)
    line_ids = fields.One2many(
        comodel_name='ages.material.consumption.return.line',
        inverse_name='wizard_id',
        string='Products to Return',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        consumption = self.env['ages.material.consumption'].browse(
            self.env.context.get('active_id')
        )
        if not consumption or consumption.state != 'done':
            return res
        res['consumption_id'] = consumption.id
        lines = []
        for line in consumption.line_ids:
            remaining = line.quantity - line.qty_returned
            if float_is_zero(remaining, precision_rounding=line.uom_id.rounding or 0.01):
                continue
            lines.append(Command.create({
                'consumption_line_id': line.id,
                'quantity_done': line.quantity,
                'qty_returned': line.qty_returned,
                'quantity': remaining,
            }))
        res['line_ids'] = lines
        return res

    def action_return(self):
        """Create reverse stock moves and reverse journal entry for returned qty."""
        self.ensure_one()
        consumption = self.consumption_id
        if consumption.state != 'done':
            raise UserError(_('Returns are only allowed on Done Material Consumptions.'))

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        return_lines = self.line_ids.filtered(
            lambda l: not float_is_zero(l.quantity, precision_digits=precision)
        )
        if not return_lines:
            raise UserError(_('Please set a return quantity greater than zero on at least one product.'))

        for line in return_lines:
            remaining = line.quantity_done - line.qty_returned
            if float_compare(line.quantity, remaining, precision_digits=precision) > 0:
                raise UserError(_(
                    'You cannot return more than the remaining quantity for %(product)s.\n'
                    'Remaining: %(remaining)s, Requested: %(requested)s',
                    product=line.product_id.display_name,
                    remaining=remaining,
                    requested=line.quantity,
                ))
            if float_compare(line.quantity, 0.0, precision_digits=precision) <= 0:
                raise UserError(_(
                    'Return quantity must be positive for %s.',
                    line.product_id.display_name,
                ))

        stock_moves = consumption._create_return_stock_moves(return_lines)
        consumption._create_and_post_return_journal_entry(return_lines, stock_moves)

        for line in return_lines:
            line.consumption_line_id.qty_returned += line.quantity

        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Consumption'),
            'res_model': 'ages.material.consumption',
            'res_id': consumption.id,
            'view_mode': 'form',
            'target': 'current',
        }


class AgesMaterialConsumptionReturnLine(models.TransientModel):
    _name = 'ages.material.consumption.return.line'
    _description = 'Material Consumption Return Line'

    wizard_id = fields.Many2one(
        comodel_name='ages.material.consumption.return',
        required=True,
        ondelete='cascade',
    )
    consumption_line_id = fields.Many2one(
        comodel_name='ages.material.consumption.line',
        string='Consumption Line',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        related='consumption_line_id.product_id',
        string='Product',
        readonly=True,
    )
    uom_id = fields.Many2one(
        related='consumption_line_id.uom_id',
        string='UOM',
        readonly=True,
    )
    quantity_done = fields.Float(
        string='Consumed',
        digits='Product Unit of Measure',
        readonly=True,
    )
    qty_returned = fields.Float(
        string='Already Returned',
        digits='Product Unit of Measure',
        readonly=True,
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Fill readonly qty fields when the web client omits them on wizard save."""
        Line = self.env['ages.material.consumption.line']
        for vals in vals_list:
            # Related product/uom come from consumption_line_id; strip any stale writes.
            vals.pop('product_id', None)
            vals.pop('uom_id', None)
            cons_line = Line.browse(vals.get('consumption_line_id')).exists()
            if not cons_line:
                continue
            if 'quantity_done' not in vals:
                vals['quantity_done'] = cons_line.quantity
            if 'qty_returned' not in vals:
                vals['qty_returned'] = cons_line.qty_returned
        return super().create(vals_list)

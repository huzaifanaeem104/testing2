# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    gate_pass_required = fields.Boolean(
        related='picking_type_id.ages_require_gate_pass',
        string='Gate Pass Required',
    )
    gate_pass_cleared = fields.Boolean(
        string='Gate Pass Cleared',
        compute='_compute_gate_pass_cleared',
    )

    @api.depends('gate_pass_id', 'gate_pass_ids', 'gate_pass_id.state', 'gate_pass_ids.state')
    def _compute_gate_pass_cleared(self):
        for picking in self:
            passes = picking.gate_pass_ids | picking.gate_pass_id
            picking.gate_pass_cleared = bool(passes.filtered(lambda g: g.state == 'posted'))

    # -------------------------------------------------------------------------
    # Hard control: no validation without a cleared Gate Pass, per operation type
    # -------------------------------------------------------------------------
    def button_validate(self):
        self._check_gate_pass_required()
        return super().button_validate()

    def _check_gate_pass_required(self):
        for picking in self:
            if not picking.picking_type_id.ages_require_gate_pass:
                continue
            passes = picking.gate_pass_ids | picking.gate_pass_id
            cleared = passes.filtered(lambda g: g.state == 'posted')
            if not cleared:
                raise UserError(_(
                    'You cannot validate "%(picking)s". Operation type '
                    '"%(type)s" requires a cleared Gate Pass before this '
                    'transfer can be completed. Create/select a Gate Pass '
                    'while this transfer is still in Draft or Ready, and '
                    'post it, before validating.',
                    picking=picking.name,
                    type=picking.picking_type_id.display_name,
                ))

    # -------------------------------------------------------------------------
    # Gate Pass creation is only allowed before the transfer is Done/Cancelled
    # -------------------------------------------------------------------------
    def action_create_gate_pass(self):
        """Create a Gate Pass from GRN (incoming) or Delivery (outgoing)."""
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_(
                'A Gate Pass can only be created while this transfer is in '
                'Draft or Ready — select the relevant transfer before it is '
                'Done, then post the Gate Pass, then validate the transfer.'
            ))
        if not self.move_ids:
            raise UserError(_('This transfer has no product moves to put on a Gate Pass.'))

        gate_type = 'in'
        if self.picking_type_code == 'outgoing':
            gate_type = 'out'
        elif self.picking_type_code == 'internal':
            gate_type = 'internal_out'
        elif self.picking_type_code == 'incoming':
            gate_type = 'in'

        lines = []
        for move in self.move_ids.filtered(lambda m: m.product_id):
            qty = move.quantity or move.product_uom_qty
            lines.append((0, 0, {
                'product_id': move.product_id.id,
                'name': move.product_id.display_name,
                'uom_id': move.product_uom.id,
                'quantity': move.product_uom_qty,
                'confirm_qty': qty,
                'move_id': move.id,
            }))

        gate_pass = self.env['ages.gate.pass'].create({
            'gate_type': gate_type,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'picking_id': self.id,
            'picking_ids': [(6, 0, [self.id])],
            'warehouse_id': self.picking_type_id.warehouse_id.id,
            'pass_date': fields.Datetime.now(),
            'line_ids': lines,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Gate Pass'),
            'res_model': 'ages.gate.pass',
            'res_id': gate_pass.id,
            'view_mode': 'form',
            'target': 'current',
        }

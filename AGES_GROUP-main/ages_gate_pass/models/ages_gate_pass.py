# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


GATE_TYPE_SEQUENCE = {
    'in': 'gate.pass.in.sequence',
    'out': 'gate.pass.out.sequence',
    'rgp': 'gate.pass.rgp.sequence',
}


class AgesGatePass(models.Model):
    _name = 'ages.gate.pass'
    _description = 'Gate Pass'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    gate_type = fields.Selection(
        selection=[
            ('in', 'Gate IN'),
            ('out', 'Gate OUT'),
            ('rgp', 'Returnable Gate Pass'),
        ],
        string='Gate Type',
        required=True,
        default='in',
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        tracking=True,
        check_company=True,
    )
    truck_no = fields.Char(string='Truck No')
    receiver = fields.Char(string='Receiver')
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='GRN Document',
        tracking=True,
        check_company=True,
        domain="[('picking_type_code', 'in', ('incoming', 'outgoing', 'internal')), ('company_id', '=', company_id)]",
    )
    pass_date = fields.Datetime(
        string='Pass Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )

    # ---- Edit approval workflow ----
    edit_request_state = fields.Selection(
        selection=[
            ('none', 'None'),
            ('requested', 'Edit Requested'),
            ('approved', 'Edit Approved'),
        ],
        string='Edit Request',
        default='none',
        copy=False,
        tracking=True,
    )
    edit_requested_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Edit Requested By',
        copy=False,
        readonly=True,
    )
    edit_approved_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Edit Approved By',
        copy=False,
        readonly=True,
    )
    is_locked = fields.Boolean(
        string='Locked',
        compute='_compute_is_locked',
    )
    can_edit_fields = fields.Boolean(
        string='Can Edit Fields',
        compute='_compute_can_edit_fields',
    )

    line_ids = fields.One2many(
        comodel_name='ages.gate.pass.line',
        inverse_name='gate_pass_id',
        string='Products',
        copy=True,
    )
    grn_count = fields.Integer(
        string='GRN Count',
        compute='_compute_grn_count',
    )
    notes = fields.Text(string='Notes')

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------
    @api.depends('picking_id')
    def _compute_grn_count(self):
        for rec in self:
            rec.grn_count = 1 if rec.picking_id else 0

    def _sync_picking_gate_passes(self):
        """Keep GRN ↔ Gate Pass many2many tags in sync with GRN Document."""
        for rec in self:
            if not rec.picking_id:
                continue
            if rec.id not in rec.picking_id.gate_pass_ids.ids:
                rec.picking_id.sudo().write({
                    'gate_pass_ids': [(4, rec.id)],
                    'gate_pass_id': rec.picking_id.gate_pass_id.id or rec.id,
                })

    @api.depends('state', 'edit_request_state')
    def _compute_is_locked(self):
        for rec in self:
            rec.is_locked = rec.state == 'posted' and rec.edit_request_state != 'approved'

    @api.depends('state', 'edit_request_state')
    def _compute_can_edit_fields(self):
        is_approver = self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval')
        for rec in self:
            if rec.state == 'draft':
                rec.can_edit_fields = True
            elif is_approver:
                rec.can_edit_fields = True
            else:
                rec.can_edit_fields = (
                    rec.state == 'posted' and rec.edit_request_state == 'approved'
                )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) in (False, _('New')):
                gate_type = vals.get('gate_type') or 'in'
                vals['name'] = self._next_sequence_name(gate_type)
        records = super().create(vals_list)
        records._sync_picking_gate_passes()
        return records

    def write(self, vals):
        restricted_keys = set(vals) - {
            'edit_request_state',
            'edit_requested_by_id',
            'edit_approved_by_id',
            'message_main_attachment_id',
        }
        if restricted_keys:
            for rec in self:
                if rec.state != 'posted':
                    continue
                if self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval'):
                    continue
                if rec.edit_request_state == 'approved':
                    continue
                raise AccessError(_(
                    'You cannot edit posted Gate Pass %(name)s.\n'
                    'Request edit access and wait for approval from an Edit Approval user.',
                    name=rec.display_name,
                ))
        res = super().write(vals)
        if 'picking_id' in vals:
            self._sync_picking_gate_passes()
        # One-shot edit: after a successful business edit while approved, consume approval.
        if self.env.context.get('skip_gate_pass_edit_consume'):
            return res
        consume = restricted_keys - {'state', 'name'}
        if consume:
            approved = self.filtered(
                lambda r: r.state == 'posted' and r.edit_request_state == 'approved'
            )
            if approved and not self.env.user.has_group(
                'ages_gate_pass.group_gate_pass_edit_approval'
            ):
                approved.with_context(skip_gate_pass_edit_consume=True).write({
                    'edit_request_state': 'none',
                    'edit_requested_by_id': False,
                    'edit_approved_by_id': False,
                })
        return res

    def unlink(self):
        if any(rec.state == 'posted' for rec in self):
            raise UserError(_('You cannot delete a Posted Gate Pass. Reset it to Draft first.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Business
    # -------------------------------------------------------------------------
    @api.model
    def _next_sequence_name(self, gate_type):
        code = GATE_TYPE_SEQUENCE.get(gate_type, 'gate.pass.in.sequence')
        name = self.env['ir.sequence'].next_by_code(code)
        if not name:
            raise UserError(_(
                'Missing sequence %(code)s. Configure it under Settings → Technical → Sequences.',
                code=code,
            ))
        return name

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.line_ids:
                raise UserError(_('Add at least one product line before posting.'))
            rec.write({
                'state': 'posted',
                'edit_request_state': 'none',
                'edit_requested_by_id': False,
                'edit_approved_by_id': False,
            })
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval'):
            raise AccessError(_(
                'Only users in the Gate Pass Edit Approval group can reset to draft.'
            ))
        for rec in self:
            rec.write({
                'state': 'draft',
                'edit_request_state': 'none',
                'edit_requested_by_id': False,
                'edit_approved_by_id': False,
            })
        return True

    def action_request_edit_access(self):
        """Edit-group users request one-time edit access on a posted gate pass."""
        if not self.env.user.has_group('ages_gate_pass.group_gate_pass_edit'):
            raise AccessError(_('You need the Gate Pass Edit group to request edit access.'))
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Edit access can only be requested on Posted gate passes.'))
            if rec.edit_request_state == 'requested':
                raise UserError(_('An edit request is already pending for %s.') % rec.display_name)
            if rec.edit_request_state == 'approved':
                raise UserError(_('Edit access is already approved for %s.') % rec.display_name)
            rec.write({
                'edit_request_state': 'requested',
                'edit_requested_by_id': self.env.user.id,
                'edit_approved_by_id': False,
            })
            rec.message_post(body=_(
                'Edit access requested by %s.',
                self.env.user.display_name,
            ))
            # Schedule activity for approval users
            approver_group = self.env.ref('ages_gate_pass.group_gate_pass_edit_approval')
            for user in approver_group.users[:5]:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Approve Gate Pass edit request'),
                    note=_('%(user)s requested edit access on %(gate_pass)s.',
                           user=self.env.user.display_name,
                           gate_pass=rec.display_name),
                )
        return True

    def action_approve_edit_access(self):
        if not self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval'):
            raise AccessError(_('Only Edit Approval users can approve edit access.'))
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only Posted gate passes can receive edit approval.'))
            if rec.edit_request_state != 'requested':
                raise UserError(_('No pending edit request on %s.') % rec.display_name)
            rec.write({
                'edit_request_state': 'approved',
                'edit_approved_by_id': self.env.user.id,
            })
            rec.activity_feedback(['mail.mail_activity_data_todo'])
            rec.message_post(body=_(
                'Edit access approved by %(approver)s for %(requester)s. '
                'They may edit once; approval is cleared after the next save.',
                approver=self.env.user.display_name,
                requester=rec.edit_requested_by_id.display_name or _('the requester'),
            ))
        return True

    def action_refuse_edit_access(self):
        if not self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval'):
            raise AccessError(_('Only Edit Approval users can refuse edit access.'))
        for rec in self:
            rec.write({
                'edit_request_state': 'none',
                'edit_requested_by_id': False,
                'edit_approved_by_id': False,
            })
            rec.activity_feedback(['mail.mail_activity_data_todo'])
            rec.message_post(body=_(
                'Edit access refused by %s.',
                self.env.user.display_name,
            ))
        return True

    def action_view_grn(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No GRN document is linked to this Gate Pass.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('GRN Document'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.onchange('picking_id')
    def _onchange_picking_id(self):
        if not self.picking_id:
            return
        picking = self.picking_id
        if picking.partner_id and not self.partner_id:
            self.partner_id = picking.partner_id
        if picking.company_id:
            self.company_id = picking.company_id
        if self.line_ids:
            return
        lines = []
        for move in picking.move_ids.filtered(lambda m: m.product_id):
            lines.append((0, 0, {
                'product_id': move.product_id.id,
                'name': move.product_id.display_name,
                'uom_id': move.product_uom.id,
                'quantity': move.product_uom_qty,
                'confirm_qty': move.quantity or move.product_uom_qty,
            }))
        self.line_ids = lines

    @api.onchange('gate_type')
    def _onchange_gate_type(self):
        # Name is assigned on create; warn visually only for draft "New" records
        return

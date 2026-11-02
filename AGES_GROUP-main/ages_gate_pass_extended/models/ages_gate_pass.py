# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare


class AgesGatePass(models.Model):
    _inherit = 'ages.gate.pass'

    state = fields.Selection(
        selection_add=[
            ('waiting_security', 'Waiting Security'),
            ('rejected', 'Rejected'),
        ],
        ondelete={
            'waiting_security': 'set default',
            'rejected': 'set default',
        },
    )

    # New Gate Pass sub-types, in addition to whatever the base module ships
    # (typically 'in' / 'out' / 'rgp'). Each new type narrows what is
    # mandatory and how the record is reported.
    gate_type = fields.Selection(
        selection_add=[
            ('internal_out', 'Internal Transfer – Out'),
            ('internal_in', 'Internal Transfer – In'),
            ('sale_return', 'Sales Return'),
            ('subcontract_return', 'Subcontract Return'),
            ('misc', 'Miscellaneous (No Stock Impact)'),
        ],
        ondelete={
            'internal_out': 'set default',
            'internal_in': 'set default',
            'sale_return': 'set default',
            'subcontract_return': 'set default',
            'misc': 'set default',
        },
    )

    # Multi document links
    picking_ids = fields.Many2many(
        comodel_name='stock.picking',
        relation='ages_gate_pass_stock_picking_rel',
        column1='gate_pass_id',
        column2='picking_id',
        string='Linked Transfers',
        check_company=True,
        help='One or more GRN / Delivery documents covered by this Gate Pass.',
    )
    # Dimensions / logistics
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        check_company=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        check_company=True,
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
    )
    sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        check_company=True,
        tracking=True,
    )
    driver_name = fields.Char(string='Driver Name', tracking=True)
    driver_phone = fields.Char(string='Driver Phone')
    vehicle_type = fields.Char(string='Vehicle Type')

    # Photos / documents
    truck_image = fields.Binary(string='Truck Photo', attachment=True)
    document_image = fields.Binary(string='Document Photo', attachment=True)
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='ages_gate_pass_ir_attachment_rel',
        column1='gate_pass_id',
        column2='attachment_id',
        string='Attachments',
    )

    # Security desk
    security_required = fields.Boolean(
        string='Requires Security Clearance',
        default=lambda self: self.env.company.ages_gate_pass_security_required,
        tracking=True,
        help='If enabled, this specific Gate Pass must go through Waiting '
             'Security before it can be Posted. Defaults from the company '
             'setting but can be overridden per record before it is posted '
             '(e.g. a low-risk Miscellaneous pass, or forcing clearance on '
             'a high-value RGP).',
    )
    security_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Security Cleared By',
        copy=False,
        readonly=True,
    )
    security_date = fields.Datetime(string='Security Date', copy=False, readonly=True)
    reject_reason = fields.Text(string='Reject Reason', copy=False, readonly=True)

    # Gate log — physical vehicle in/out, independent of paperwork state
    gate_in_datetime = fields.Datetime(string='Gate In', tracking=True, copy=False)
    gate_out_datetime = fields.Datetime(string='Gate Out', tracking=True, copy=False)
    duration_display = fields.Char(string='Time at Gate', compute='_compute_duration')

    # Internal Transfer pairing (Main Store -> Site, etc.)
    outward_gate_pass_id = fields.Many2one(
        comodel_name='ages.gate.pass',
        string='Outward Reference',
        domain=[('gate_type', 'in', ('out', 'internal_out'))],
        check_company=True,
        help='For an Internal Transfer – In Gate Pass, the matching Outward '
             'Gate Pass created when the goods left the source location. '
             'Used to compare what was sent vs. what arrived.',
    )
    inward_gate_pass_ids = fields.One2many(
        comodel_name='ages.gate.pass',
        inverse_name='outward_gate_pass_id',
        string='Linked Inward Passes',
    )
    has_qty_variance = fields.Boolean(
        string='Quantity Variance', compute='_compute_variance', store=True,
    )
    variance_note = fields.Text(
        string='Variance Detail', compute='_compute_variance', store=True,
    )

    # RGP return tracking
    expected_return_date = fields.Date(string='Expected Return Date', tracking=True)
    actual_return_date = fields.Date(string='Actual Return Date', tracking=True)
    return_state = fields.Selection(
        selection=[
            ('not_applicable', 'N/A'),
            ('pending', 'Pending Return'),
            ('partial', 'Partially Returned'),
            ('returned', 'Returned'),
            ('overdue', 'Overdue'),
        ],
        string='Return Status',
        compute='_compute_return_state',
        store=True,
    )
    is_overdue = fields.Boolean(compute='_compute_return_state', store=True)
    source_rgp_id = fields.Many2one(
        comodel_name='ages.gate.pass',
        string='Return Against (RGP)',
        domain=[('gate_type', '=', 'rgp')],
        check_company=True,
        copy=False,
        help='Set automatically when this Inward Gate Pass was generated '
             'from the "Return Items" action on a Returnable Gate Pass.',
    )
    return_gate_pass_ids = fields.One2many(
        comodel_name='ages.gate.pass',
        inverse_name='source_rgp_id',
        string='Return Gate Passes',
    )
    return_count = fields.Integer(compute='_compute_return_count')

    qr_code = fields.Char(
        string='QR Code',
        compute='_compute_qr_code',
    )
    grn_count = fields.Integer(compute='_compute_grn_count')

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------
    @api.depends('picking_id', 'picking_ids')
    def _compute_grn_count(self):
        for rec in self:
            rec.grn_count = len(rec.picking_ids | rec.picking_id)

    @api.depends('return_gate_pass_ids')
    def _compute_return_count(self):
        for rec in self:
            rec.return_count = len(rec.return_gate_pass_ids)

    @api.depends('name')
    def _compute_qr_code(self):
        for rec in self:
            rec.qr_code = rec.name if rec.name and rec.name != _('New') else ''

    @api.depends('gate_in_datetime', 'gate_out_datetime')
    def _compute_duration(self):
        for rec in self:
            if rec.gate_in_datetime and rec.gate_out_datetime:
                delta = rec.gate_out_datetime - rec.gate_in_datetime
                total_minutes = int(delta.total_seconds() // 60)
                hours, minutes = divmod(total_minutes, 60)
                rec.duration_display = _('%(h)dh %(m)dm') % {'h': hours, 'm': minutes}
            elif rec.gate_in_datetime:
                rec.duration_display = _('Vehicle inside')
            else:
                rec.duration_display = ''

    @api.depends(
        'outward_gate_pass_id',
        'outward_gate_pass_id.line_ids.confirm_qty',
        'outward_gate_pass_id.line_ids.product_id',
        'line_ids.confirm_qty',
        'line_ids.product_id',
    )
    def _compute_variance(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for rec in self:
            if not rec.outward_gate_pass_id:
                rec.has_qty_variance = False
                rec.variance_note = False
                continue
            sent = {}
            for line in rec.outward_gate_pass_id.line_ids.filtered('product_id'):
                sent[line.product_id] = sent.get(line.product_id, 0.0) + line.confirm_qty
            received = {}
            for line in rec.line_ids.filtered('product_id'):
                received[line.product_id] = received.get(line.product_id, 0.0) + line.confirm_qty
            notes = []
            variance = False
            for product in set(sent) | set(received):
                sent_qty = sent.get(product, 0.0)
                recv_qty = received.get(product, 0.0)
                if float_compare(sent_qty, recv_qty, precision_digits=precision) != 0:
                    variance = True
                    notes.append(_(
                        '%(product)s: sent %(sent)s, received %(recv)s (diff %(diff)s)',
                        product=product.display_name,
                        sent=sent_qty,
                        recv=recv_qty,
                        diff=recv_qty - sent_qty,
                    ))
            rec.has_qty_variance = variance
            rec.variance_note = '\n'.join(notes) if notes else False

    @api.depends(
        'gate_type',
        'state',
        'expected_return_date',
        'actual_return_date',
        'line_ids.confirm_qty',
        'line_ids.qty_returned',
    )
    def _compute_return_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.gate_type != 'rgp':
                rec.return_state = 'not_applicable'
                rec.is_overdue = False
                continue
            if rec.state not in ('posted', 'waiting_security'):
                rec.return_state = 'pending' if rec.state == 'draft' else 'not_applicable'
                rec.is_overdue = False
                continue
            total = sum(rec.line_ids.mapped('confirm_qty'))
            returned = sum(rec.line_ids.mapped('qty_returned'))
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            if float_compare(returned, total, precision_digits=precision) >= 0 and total:
                rec.return_state = 'returned'
                rec.is_overdue = False
            elif float_compare(returned, 0.0, precision_digits=precision) > 0:
                overdue = bool(rec.expected_return_date and rec.expected_return_date < today and not rec.actual_return_date)
                rec.return_state = 'overdue' if overdue else 'partial'
                rec.is_overdue = overdue
            else:
                overdue = bool(rec.expected_return_date and rec.expected_return_date < today)
                rec.return_state = 'overdue' if overdue else 'pending'
                rec.is_overdue = overdue

    @api.depends('state', 'edit_request_state')
    def _compute_is_locked(self):
        for rec in self:
            rec.is_locked = (
                rec.state in ('posted', 'waiting_security', 'rejected')
                and rec.edit_request_state != 'approved'
            )

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
    # CRUD / helpers
    # -------------------------------------------------------------------------
    @api.model
    def _next_sequence_name(self, gate_type, company=None):
        """Company-aware sequence (falls back to shared sequence)."""
        company = company or self.env.company
        code = {
            'in': 'gate.pass.in.sequence',
            'out': 'gate.pass.out.sequence',
            'internal_in': 'gate.pass.in.sequence',
            'internal_out': 'gate.pass.out.sequence',
            'sale_return': 'gate.pass.in.sequence',
            'subcontract_return': 'gate.pass.in.sequence',
            'misc': 'gate.pass.in.sequence',
            'rgp': 'gate.pass.rgp.sequence',
        }.get(gate_type, 'gate.pass.in.sequence')
        name = self.env['ir.sequence'].with_company(company).next_by_code(code)
        if not name:
            name = self.env['ir.sequence'].next_by_code(code)
        if not name:
            raise UserError(_(
                'Missing sequence %(code)s. Configure it under Settings → Technical → Sequences.',
                code=code,
            ))
        return name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = (
                self.env['res.company'].browse(vals['company_id'])
                if vals.get('company_id') else self.env.company
            )
            if vals.get('name', _('New')) in (False, _('New')):
                vals['name'] = self._next_sequence_name(vals.get('gate_type') or 'in', company)
            if vals.get('gate_type') == 'rgp' and not vals.get('expected_return_date'):
                days = company.ages_gate_pass_rgp_default_days or 7
                vals['expected_return_date'] = fields.Date.context_today(self) + timedelta(days=days)
            if 'security_required' not in vals:
                vals['security_required'] = company.ages_gate_pass_security_required
        records = super().create(vals_list)
        for rec in records:
            if rec.picking_id and rec.picking_id not in rec.picking_ids:
                rec.with_context(
                    skip_gate_pass_edit_consume=True,
                    skip_gate_pass_lock=True,
                ).write({'picking_ids': [(4, rec.picking_id.id)]})
            elif rec.picking_ids and not rec.picking_id:
                rec.with_context(
                    skip_gate_pass_edit_consume=True,
                    skip_gate_pass_lock=True,
                ).write({'picking_id': rec.picking_ids[:1].id})
            rec._sync_picking_gate_passes()
        return records

    def write(self, vals):
        # Extend lock to waiting_security / rejected
        restricted_keys = set(vals) - {
            'edit_request_state',
            'edit_requested_by_id',
            'edit_approved_by_id',
            'message_main_attachment_id',
            'security_user_id',
            'security_date',
            'reject_reason',
            'return_state',
            'actual_return_date',
            'gate_in_datetime',
            'gate_out_datetime',
        }
        if restricted_keys and not self.env.context.get('skip_gate_pass_lock'):
            for rec in self:
                if rec.state not in ('posted', 'waiting_security', 'rejected'):
                    continue
                if self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval'):
                    continue
                if rec.state == 'posted' and rec.edit_request_state == 'approved':
                    continue
                if rec.state == 'waiting_security' and self.env.user.has_group(
                    'ages_gate_pass_extended.group_gate_pass_security'
                ):
                    # security may only change state via dedicated actions
                    if restricted_keys - {'state'}:
                        raise AccessError(_(
                            'Waiting Security Gate Pass %(name)s can only be cleared by Security actions.',
                            name=rec.display_name,
                        ))
                    continue
                raise AccessError(_(
                    'You cannot edit Gate Pass %(name)s in state %(state)s without approval.',
                    name=rec.display_name,
                    state=rec.state,
                ))
        res = super(AgesGatePass, self).write(vals)
        if 'picking_id' in vals or 'picking_ids' in vals:
            for rec in self:
                if rec.picking_id and rec.picking_id not in rec.picking_ids:
                    rec.with_context(skip_gate_pass_edit_consume=True, skip_gate_pass_lock=True).write({
                        'picking_ids': [(4, rec.picking_id.id)],
                    })
                rec._sync_picking_gate_passes()
        return res

    def _sync_picking_gate_passes(self):
        for rec in self:
            for picking in rec.picking_ids | rec.picking_id:
                vals = {}
                if rec.id not in picking.gate_pass_ids.ids:
                    vals['gate_pass_ids'] = [(4, rec.id)]
                if not picking.gate_pass_id:
                    vals['gate_pass_id'] = rec.id
                if vals:
                    picking.sudo().write(vals)

    def unlink(self):
        if any(rec.state in ('posted', 'waiting_security') for rec in self):
            raise UserError(_('You cannot delete a Posted / Waiting Security Gate Pass.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Qty vs transfers
    # -------------------------------------------------------------------------
    def _get_linked_pickings(self):
        self.ensure_one()
        return self.picking_ids | self.picking_id

    def _get_product_remaining_qty(self, product, uom=None):
        """Remaining qty on linked pickings not yet confirmed on other posted passes."""
        self.ensure_one()
        pickings = self._get_linked_pickings()
        if not pickings or not product:
            return None
        demand = 0.0
        for picking in pickings:
            for move in picking.move_ids.filtered(lambda m: m.product_id == product):
                qty = move.quantity or move.product_uom_qty
                if uom and move.product_uom != uom:
                    qty = move.product_uom._compute_quantity(qty, uom)
                demand += qty
        # Subtract confirm qty from other non-rejected passes
        other_lines = self.env['ages.gate.pass.line'].search([
            ('product_id', '=', product.id),
            ('gate_pass_id', '!=', self.id),
            ('gate_pass_id.state', 'in', ('draft', 'waiting_security', 'posted')),
            '|',
            ('gate_pass_id.picking_id', 'in', pickings.ids),
            ('gate_pass_id.picking_ids', 'in', pickings.ids),
        ])
        used = sum(other_lines.mapped('confirm_qty'))
        return demand - used

    def _check_qty_against_pickings(self):
        for rec in self:
            if not rec.company_id.ages_gate_pass_block_qty_overflow:
                continue
            if not rec._get_linked_pickings():
                continue
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            for line in rec.line_ids.filtered('product_id'):
                remaining = rec._get_product_remaining_qty(line.product_id, line.uom_id)
                if remaining is None:
                    continue
                if float_compare(line.confirm_qty, remaining, precision_digits=precision) > 0:
                    raise UserError(_(
                        'Confirm quantity for %(product)s (%(qty)s) exceeds remaining '
                        'quantity on linked transfers (%(remaining)s).',
                        product=line.product_id.display_name,
                        qty=line.confirm_qty,
                        remaining=remaining,
                    ))

    def _check_type_requirements(self):
        """Business-rule guardrails per Gate Pass sub-type before posting."""
        for rec in self:
            pickings = rec._get_linked_pickings()
            if rec.gate_type == 'misc':
                continue  # register-only, no stock document required
            if rec.gate_type == 'rgp':
                continue  # equipment loans may have no stock document
            if not pickings:
                raise UserError(_(
                    'Gate Pass %(name)s (%(type)s) must be linked to at least one '
                    'Receipt / Delivery / Internal Transfer before it can be posted.',
                    name=rec.display_name, type=dict(
                        rec._fields['gate_type'].selection
                    ).get(rec.gate_type),
                ))
            if rec.gate_type == 'internal_in' and not rec.outward_gate_pass_id:
                rec.message_post(body=_(
                    'Warning: this Internal Transfer – In Gate Pass has no Outward '
                    'reference selected, so quantity variance cannot be checked.'
                ))

    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------
    def action_post(self):
        """Draft → Waiting Security (if enabled) or Posted."""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.line_ids and rec.gate_type != 'misc':
                raise UserError(_('Add at least one product/item line before posting.'))
            rec._check_type_requirements()
            rec._check_qty_against_pickings()
            if rec.security_required:
                rec.with_context(skip_gate_pass_lock=True).write({
                    'state': 'waiting_security',
                    'edit_request_state': 'none',
                    'edit_requested_by_id': False,
                    'edit_approved_by_id': False,
                    'reject_reason': False,
                })
                rec._notify_security_desk()
            else:
                rec._set_posted()
        return True

    def _set_posted(self):
        for rec in self:
            rec.with_context(skip_gate_pass_lock=True).write({
                'state': 'posted',
                'edit_request_state': 'none',
                'edit_requested_by_id': False,
                'edit_approved_by_id': False,
            })
            rec._apply_rgp_return_sync()
            rec._send_mail_template('ages_gate_pass_extended.mail_template_gate_pass_posted')
        return True

    def action_security_approve(self):
        if not self.env.user.has_group('ages_gate_pass_extended.group_gate_pass_security'):
            raise AccessError(_('Only Security Desk users can clear Gate Passes.'))
        for rec in self:
            if rec.state != 'waiting_security':
                raise UserError(_('Only Waiting Security passes can be approved.'))
            rec._check_qty_against_pickings()
            rec.with_context(skip_gate_pass_lock=True).write({
                'state': 'posted',
                'security_user_id': self.env.user.id,
                'security_date': fields.Datetime.now(),
                'edit_request_state': 'none',
                'edit_requested_by_id': False,
                'edit_approved_by_id': False,
            })
            rec._apply_rgp_return_sync()
            rec.activity_feedback(['mail.mail_activity_data_todo'])
            rec._send_mail_template('ages_gate_pass_extended.mail_template_gate_pass_posted')
            rec.message_post(body=_('Security cleared by %s.') % self.env.user.display_name)
        return True

    def action_security_reject_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Gate Pass'),
            'res_model': 'ages.gate.pass.reject',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_gate_pass_id': self.id},
        }

    def action_security_reject(self, reason):
        if not self.env.user.has_group('ages_gate_pass_extended.group_gate_pass_security'):
            raise AccessError(_('Only Security Desk users can reject Gate Passes.'))
        for rec in self:
            if rec.state != 'waiting_security':
                raise UserError(_('Only Waiting Security passes can be rejected.'))
            rec.with_context(skip_gate_pass_lock=True).write({
                'state': 'rejected',
                'reject_reason': reason,
                'security_user_id': self.env.user.id,
                'security_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('Rejected by %(user)s: %(reason)s',
                                    user=self.env.user.display_name, reason=reason))
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group('ages_gate_pass.group_gate_pass_edit_approval'):
            raise AccessError(_(
                'Only users in the Gate Pass Edit Approval group can reset to draft.'
            ))
        for rec in self:
            if any(picking.state == 'done' for picking in rec._get_linked_pickings()):
                raise UserError(_(
                    'This Gate Pass is linked to a completed transfer and can no '
                    'longer be reset to Draft. Use a correction / reversal instead.'
                ))
            rec.with_context(skip_gate_pass_lock=True).write({
                'state': 'draft',
                'edit_request_state': 'none',
                'edit_requested_by_id': False,
                'edit_approved_by_id': False,
                'security_user_id': False,
                'security_date': False,
                'reject_reason': False,
            })
        return True

    def action_mark_returned(self):
        """Force-close an RGP as fully returned WITHOUT a matching Gate Pass
        movement. Restricted to managers and meant only for correcting data
        entry mistakes — the normal path is action_open_return_wizard, which
        creates a real, security-clearable Inward Gate Pass."""
        if not self.env.user.has_group('ages_gate_pass_extended.group_gate_pass_manager'):
            raise AccessError(_(
                'Only Gate Pass Managers can force-close a return without an '
                'actual Return Gate Pass. Use "Return Items" instead.'
            ))
        for rec in self:
            if rec.gate_type != 'rgp':
                raise UserError(_('Only Returnable Gate Passes can be marked returned.'))
            if rec.state != 'posted':
                raise UserError(_('Only Posted RGP can be marked returned.'))
            for line in rec.line_ids:
                line.qty_returned = line.confirm_qty
            rec.with_context(skip_gate_pass_lock=True).write({
                'actual_return_date': fields.Date.context_today(self),
            })
            rec.message_post(body=_(
                'Force-closed as fully returned by %s (no Gate Pass movement recorded).'
            ) % self.env.user.display_name)
        return True

    def action_open_return_wizard(self):
        self.ensure_one()
        if self.gate_type != 'rgp':
            raise UserError(_('Only Returnable Gate Passes support this action.'))
        if self.state != 'posted':
            raise UserError(_('Only Posted RGP can be returned.'))
        if self.return_state == 'returned':
            raise UserError(_('This RGP is already fully returned.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Items'),
            'res_model': 'ages.gate.pass.return',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_rgp_id': self.id},
        }

    def _apply_rgp_return_sync(self):
        """When an Inward Gate Pass created against a source RGP is Posted,
        push the returned quantities back onto the original RGP lines."""
        for rec in self:
            if rec.gate_type not in ('in', 'internal_in') or not rec.source_rgp_id:
                continue
            rgp = rec.source_rgp_id
            for ret_line in rec.line_ids.filtered('product_id'):
                rgp_line = rgp.line_ids.filtered(lambda l: l.product_id == ret_line.product_id)[:1]
                if not rgp_line:
                    continue
                new_returned = min(
                    rgp_line.qty_returned + ret_line.confirm_qty,
                    rgp_line.confirm_qty,
                )
                rgp_line.write({'qty_returned': new_returned})
            rgp._compute_return_state()
            if rgp.return_state == 'returned' and not rgp.actual_return_date:
                rgp.with_context(skip_gate_pass_lock=True).write({
                    'actual_return_date': fields.Date.context_today(rec),
                })
            rgp.message_post(body=_(
                'Return recorded via Gate Pass %s.'
            ) % rec.display_name)

    def action_print_gate_pass(self):
        return self.env.ref('ages_gate_pass_extended.action_report_ages_gate_pass').report_action(self)

    def action_view_grn(self):
        self.ensure_one()
        pickings = self._get_linked_pickings()
        if not pickings:
            raise UserError(_('No transfer is linked to this Gate Pass.'))
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Linked Transfers'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)],
        }
        if len(pickings) == 1:
            action.update({'view_mode': 'form', 'res_id': pickings.id})
        return action

    def action_view_returns(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Return Gate Passes'),
            'res_model': 'ages.gate.pass',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.return_gate_pass_ids.ids)],
        }
        if len(self.return_gate_pass_ids) == 1:
            action.update({'view_mode': 'form', 'res_id': self.return_gate_pass_ids.id})
        return action

    # -------------------------------------------------------------------------
    # Gate log (physical vehicle in / out)
    # -------------------------------------------------------------------------
    def action_gate_in(self):
        for rec in self:
            if rec.state not in ('waiting_security', 'posted'):
                raise UserError(_(
                    'Submit the Gate Pass (Post / send to Security) before marking Gate In.'
                ))
            if rec.gate_in_datetime:
                raise UserError(_('Gate In has already been recorded for %s.') % rec.display_name)
            rec.with_context(skip_gate_pass_lock=True).write({
                'gate_in_datetime': fields.Datetime.now(),
            })
            rec.message_post(body=_('Vehicle marked IN by %s.') % self.env.user.display_name)
        return True

    def action_gate_out(self):
        for rec in self:
            if not rec.gate_in_datetime:
                raise UserError(_('Mark Gate In before Gate Out.'))
            if rec.gate_out_datetime:
                raise UserError(_('Gate Out has already been recorded for %s.') % rec.display_name)
            rec.with_context(skip_gate_pass_lock=True).write({
                'gate_out_datetime': fields.Datetime.now(),
            })
            rec.message_post(body=_('Vehicle marked OUT by %s.') % self.env.user.display_name)
        return True

    # -------------------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------------------
    def _send_mail_template(self, xmlid):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            return
        for rec in self:
            try:
                template.send_mail(rec.id, force_send=False)
            except Exception:
                # Do not block workflow if mail/partner email is missing
                continue

    def _notify_security_desk(self):
        group = self.env.ref('ages_gate_pass_extended.group_gate_pass_security', raise_if_not_found=False)
        if not group:
            return
        for rec in self:
            for user in group.users[:10]:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Security clearance required'),
                    note=_('Gate Pass %s is waiting at security.') % rec.display_name,
                )
            rec._send_mail_template('ages_gate_pass_extended.mail_template_gate_pass_security')

    def action_request_edit_access(self):
        res = super().action_request_edit_access()
        self._send_mail_template('ages_gate_pass_extended.mail_template_gate_pass_edit_request')
        return res

    def action_approve_edit_access(self):
        res = super().action_approve_edit_access()
        self._send_mail_template('ages_gate_pass_extended.mail_template_gate_pass_edit_approved')
        return res

    # -------------------------------------------------------------------------
    # Onchange / cron
    # -------------------------------------------------------------------------
    @api.onchange('picking_id')
    def _onchange_picking_id(self):
        super()._onchange_picking_id()
        if self.picking_id:
            self.picking_ids = [(4, self.picking_id.id)]
            picking = self.picking_id
            if picking.picking_type_id.warehouse_id:
                self.warehouse_id = picking.picking_type_id.warehouse_id
            if picking.picking_type_code == 'outgoing':
                self.gate_type = 'out'
            elif picking.picking_type_code == 'internal' and self.gate_type not in ('internal_in',):
                self.gate_type = 'internal_out'
            elif picking.picking_type_code == 'incoming' and self.gate_type in ('out', False):
                self.gate_type = 'in'

    @api.onchange('gate_type', 'picking_id')
    def _onchange_internal_pair(self):
        if self.gate_type == 'internal_in' and self.picking_id and not self.outward_gate_pass_id:
            candidate = self.env['ages.gate.pass'].search([
                ('gate_type', '=', 'internal_out'),
                ('picking_id', '=', self.picking_id.id),
            ], limit=1)
            if candidate:
                self.outward_gate_pass_id = candidate

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id:
            self.analytic_account_id = self.project_id.account_id
            contract = getattr(self.project_id, 'ages_contract_id', False)
            if contract and contract.sub_company_id:
                self.sub_company_id = contract.sub_company_id

    @api.onchange('gate_type')
    def _onchange_gate_type_extended(self):
        if self.gate_type == 'rgp' and not self.expected_return_date:
            days = self.company_id.ages_gate_pass_rgp_default_days or 7
            self.expected_return_date = fields.Date.context_today(self) + timedelta(days=days)

    @api.model
    def _cron_flag_overdue_rgp(self):
        today = fields.Date.context_today(self)
        passes = self.search([
            ('gate_type', '=', 'rgp'),
            ('state', '=', 'posted'),
            ('expected_return_date', '<', today),
            ('actual_return_date', '=', False),
        ])
        # Recompute stored return_state
        passes._compute_return_state()
        for rec in passes.filtered('is_overdue'):
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=rec.create_uid.id or self.env.user.id,
                summary=_('Overdue Returnable Gate Pass'),
                note=_('%s is overdue for return.') % rec.display_name,
            )

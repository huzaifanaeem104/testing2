# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class AssetTransfer(models.Model):
    _name = 'asset.transfer'
    _description = 'Asset Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Transfer Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    location_from_id = fields.Many2one(
        comodel_name='stock.location',
        string='From Location',
        required=True,
        tracking=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    location_to_id = fields.Many2one(
        comodel_name='stock.location',
        string='To Location',
        required=True,
        tracking=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    transfer_type = fields.Selection(
        selection=[
            ('main_to_site', 'Main Warehouse → Site'),
            ('site_to_site', 'Site → Site'),
            ('site_to_main', 'Site → Main Warehouse'),
            ('other', 'Other'),
        ],
        string='Transfer Type',
        compute='_compute_transfer_type',
        store=True,
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        tracking=True,
        check_company=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        tracking=True,
    )
    reason = fields.Text(string='Reason / Notes')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    line_ids = fields.One2many(
        comodel_name='asset.transfer.line',
        inverse_name='transfer_id',
        string='Assets',
        copy=True,
    )
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Stock Picking',
        copy=False,
        readonly=True,
    )
    create_stock_move = fields.Boolean(
        string='Create Stock Move',
        default=False,
        help='If enabled, create an internal transfer for assets that have a Stock Product set.',
    )

    # -------------------------------------------------------------------------
    # Compute / onchange
    # -------------------------------------------------------------------------
    @api.depends('location_from_id', 'location_to_id', 'location_from_id.ages_project_id', 'location_to_id.ages_project_id')
    def _compute_transfer_type(self):
        for rec in self:
            from_proj = bool(rec.location_from_id.ages_project_id)
            to_proj = bool(rec.location_to_id.ages_project_id)
            if not from_proj and to_proj:
                rec.transfer_type = 'main_to_site'
            elif from_proj and to_proj:
                rec.transfer_type = 'site_to_site'
            elif from_proj and not to_proj:
                rec.transfer_type = 'site_to_main'
            else:
                rec.transfer_type = 'other'

    @api.onchange('location_to_id')
    def _onchange_location_to_id(self):
        if not self.location_to_id:
            return
        project = self.location_to_id.ages_project_id
        if project:
            self.project_id = project
            self.analytic_account_id = project.account_id
        elif self.transfer_type == 'site_to_main' or (
            self.location_from_id.ages_project_id and not self.location_to_id.ages_project_id
        ):
            # Returning to main warehouse — project can be empty
            self.project_id = False
            self.analytic_account_id = False

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id:
            self.analytic_account_id = self.project_id.account_id

    @api.onchange('location_from_id')
    def _onchange_location_from_id(self):
        # Clear lines that no longer match From location
        if self.line_ids and self.location_from_id:
            invalid = self.line_ids.filtered(
                lambda line: line.asset_id.current_location_id != self.location_from_id
            )
            if invalid:
                self.line_ids = self.line_ids - invalid

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) in (False, _('New')):
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.transfer') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            if rec.state == 'done' and not self.env.context.get('ages_asset_transfer_force'):
                raise UserError(_(
                    'Transfer %(name)s is Done and locked. No further edits are allowed.',
                    name=rec.display_name,
                ))
        return super().write(vals)

    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise UserError(_('You cannot delete a Done Asset Transfer.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Validations
    # -------------------------------------------------------------------------
    def _check_lines(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Add at least one asset line.'))
            if rec.location_from_id == rec.location_to_id:
                raise UserError(_('From and To locations must be different.'))
            for line in rec.line_ids:
                asset = line.asset_id
                if not asset:
                    raise UserError(_('Each line must have an asset.'))
                if asset.current_location_id != rec.location_from_id:
                    raise UserError(_(
                        'Asset %(asset)s is currently in %(current)s, not in From location %(from_loc)s.',
                        asset=asset.display_name,
                        current=asset.current_location_id.display_name or _('(no location)'),
                        from_loc=rec.location_from_id.display_name,
                    ))
                # Soft lock: asset already on another open transfer
                other = self.env['asset.transfer.line'].search([
                    ('asset_id', '=', asset.id),
                    ('transfer_id', '!=', rec.id),
                    ('transfer_id.state', 'in', ('draft', 'confirmed')),
                ], limit=1)
                if other:
                    raise UserError(_(
                        'Asset %(asset)s is already on open transfer %(transfer)s.',
                        asset=asset.display_name,
                        transfer=other.transfer_id.display_name,
                    ))

    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------
    def action_confirm(self):
        if not self.env.user.has_group('ages_asset_transfer.group_asset_transfer_user'):
            raise AccessError(_('You are not allowed to confirm Asset Transfers.'))
        for rec in self:
            if rec.state != 'draft':
                continue
            rec._check_lines()
            rec.state = 'confirmed'
        return True

    def action_validate(self):
        """Validate → done: update locations, history, optional stock move, lock."""
        if not self.env.user.has_group('ages_asset_transfer.group_asset_transfer_manager'):
            raise AccessError(_('Only Warehouse / Asset Managers can validate Asset Transfers.'))
        for rec in self:
            if rec.state not in ('draft', 'confirmed'):
                continue
            if rec.state == 'draft':
                rec._check_lines()
            else:
                rec._check_lines()
            rec._apply_transfer()
            rec.with_context(ages_asset_transfer_force=True).write({'state': 'done'})
        return True

    def action_cancel(self):
        if not self.env.user.has_group('ages_asset_transfer.group_asset_transfer_manager'):
            raise AccessError(_('Only Warehouse / Asset Managers can cancel Asset Transfers.'))
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('You cannot cancel a Done transfer.'))
            rec.state = 'cancelled'
        return True

    def action_draft(self):
        for rec in self:
            if rec.state not in ('confirmed', 'cancelled'):
                raise UserError(_('Only Confirmed or Cancelled transfers can be reset to Draft.'))
            rec.state = 'draft'
        return True

    def _apply_transfer(self):
        self.ensure_one()
        History = self.env['asset.transfer.history']
        for line in self.line_ids:
            asset = line.asset_id
            location_from = self.location_from_id
            location_to = self.location_to_id
            asset.with_context(ages_asset_transfer_force=True).write({
                'current_location_id': location_to.id,
            })
            History.create({
                'transfer_id': self.id,
                'asset_id': asset.id,
                'date': self.date,
                'location_from_id': location_from.id,
                'location_to_id': location_to.id,
                'project_id': self.project_id.id,
                'reason': self.reason,
                'user_id': self.env.user.id,
                'company_id': self.company_id.id,
            })
            asset.message_post(body=_(
                'Transferred from %(from_loc)s to %(to_loc)s via Transfer No. %(transfer)s',
                from_loc=location_from.display_name,
                to_loc=location_to.display_name,
                transfer=self.name,
            ))
        if self.create_stock_move:
            self._create_internal_picking()

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No stock picking is linked to this transfer.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Picking'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_internal_picking(self):
        """Optional internal picking for assets linked to a stock product."""
        self.ensure_one()
        moves_vals = []
        for line in self.line_ids.filtered(lambda l: l.asset_id.product_id):
            product = line.asset_id.product_id
            moves_vals.append((0, 0, {
                'name': product.display_name,
                'product_id': product.id,
                'product_uom_qty': line.quantity or 1.0,
                'product_uom': product.uom_id.id,
                'location_id': self.location_from_id.id,
                'location_dest_id': self.location_to_id.id,
                'company_id': self.company_id.id,
            }))
        if not moves_vals:
            return False

        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        picking_type = warehouse.int_type_id if warehouse else self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No internal operation type found to create a stock move for this Asset Transfer.'
            ))
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.location_from_id.id,
            'location_dest_id': self.location_to_id.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'move_ids': moves_vals,
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        self.with_context(ages_asset_transfer_force=True).picking_id = picking.id
        return picking

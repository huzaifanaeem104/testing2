from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .stock_utils import check_available, check_valuation_config, move_cost, post_stock_move


class DairyFeedConsumption(models.Model):
    """Actual feed issued to an animal or a group.

    Validation posts exactly one standard stock move from the feed store to
    the consumption (or wastage) location; quantities and valuation are owned
    by Inventory. A posted record is never edited: it is reversed with a
    return move and a documented reason.
    """
    _name = 'dairy.feed.consumption'
    _description = 'Feed Consumption'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(required=True, default=fields.Date.context_today, index=True, tracking=True)
    shift_id = fields.Many2one('dairy.shift', check_company=True)
    consumption_type = fields.Selection([
        ('feeding', 'Feeding'),
        ('wastage', 'Wastage / Spoilage'),
    ], required=True, default='feeding', tracking=True)
    allocation_type = fields.Selection([('group', 'Animal Group'), ('animal', 'Individual Animal')],
                                       required=True, default='group')
    group_id = fields.Many2one('dairy.animal.group', check_company=True, index=True)
    animal_id = fields.Many2one('dairy.animal', check_company=True, index=True, ondelete='restrict')
    allocated_animal_ids = fields.Many2many('dairy.animal', 'dairy_feed_consumption_animal_rel',
                                            'consumption_id', 'animal_id', string='Allocated Animals',
                                            readonly=True, copy=False,
                                            help='Animals the cost was allocated to when the record was posted.')
    head_count = fields.Integer(readonly=True, copy=False)
    plan_id = fields.Many2one('dairy.feed.plan', index=True, check_company=True)
    plan_line_id = fields.Many2one('dairy.feed.plan.line', index=True)
    product_id = fields.Many2one('product.product', string='Feed', required=True, check_company=True,
                                 domain="[('is_dairy_feed', '=', True)]", tracking=True)
    lot_id = fields.Many2one('stock.lot', string='Lot', check_company=True,
                             domain="[('product_id', '=', product_id)]")
    tracking = fields.Selection(related='product_id.tracking')
    planned_qty = fields.Float(digits='Product Unit of Measure')
    actual_qty = fields.Float(required=True, digits='Product Unit of Measure', tracking=True)
    variance_qty = fields.Float(compute='_compute_variance', digits='Product Unit of Measure')
    product_qty = fields.Float(string='Qty (Product Unit)', readonly=True, copy=False,
                               digits='Product Unit of Measure')
    product_uom_id = fields.Many2one(related='product_id.uom_id', string='Product Unit')
    uom_id = fields.Many2one('uom.uom', string='Unit', required=True,
                             compute='_compute_uom_id', store=True, readonly=False, precompute=True)
    uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    location_id = fields.Many2one('stock.location', string='Source Location', check_company=True,
                                  compute='_compute_locations', store=True, readonly=False, precompute=True,
                                  domain="[('usage', '=', 'internal')]")
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', check_company=True,
                                       compute='_compute_locations', store=True, readonly=False, precompute=True,
                                       domain="[('usage', '=', 'inventory')]")
    move_id = fields.Many2one('stock.move', string='Stock Move', readonly=True, copy=False, index=True)
    reversal_move_id = fields.Many2one('stock.move', string='Reversal Move', readonly=True, copy=False)
    cost_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id',
                                  help='Inventory value of the issued quantity (from stock valuation).')
    cost_per_head = fields.Monetary(compute='_compute_cost_per_head', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    responsible_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Posted'),
        ('reversed', 'Reversed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True, index=True)
    correction_reason = fields.Text(copy=False, tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('actual_qty_positive', 'CHECK(actual_qty > 0)', 'The consumed quantity must be positive.'),
        ('planned_qty_positive', 'CHECK(planned_qty IS NULL OR planned_qty >= 0)', 'The planned quantity cannot be negative.'),
        ('move_uniq', 'unique(move_id)', 'A stock move can only be linked to one feed record.'),
    ]

    # ------------------------------------------------------------------
    @api.depends('product_id')
    def _compute_uom_id(self):
        for rec in self:
            if rec.product_id and (not rec.uom_id or rec.uom_id.category_id != rec.product_id.uom_id.category_id):
                rec.uom_id = rec.product_id.uom_id

    @api.depends('consumption_type', 'company_id')
    def _compute_locations(self):
        for rec in self:
            company = rec.company_id or self.env.company
            if not rec.location_id:
                rec.location_id = company.dairy_feed_location_id
            rec.location_dest_id = (company.dairy_feed_wastage_location_id if rec.consumption_type == 'wastage'
                                    else company.dairy_feed_consumption_location_id)

    @api.depends('planned_qty', 'actual_qty')
    def _compute_variance(self):
        for rec in self:
            rec.variance_qty = rec.actual_qty - rec.planned_qty if rec.planned_qty else 0.0

    @api.depends('cost_amount', 'head_count')
    def _compute_cost_per_head(self):
        for rec in self:
            rec.cost_per_head = rec.cost_amount / rec.head_count if rec.head_count else rec.cost_amount

    @api.constrains('allocation_type', 'group_id', 'animal_id', 'consumption_type')
    def _check_allocation(self):
        for rec in self:
            if rec.consumption_type == 'wastage':
                continue
            if rec.allocation_type == 'group' and not rec.group_id:
                raise ValidationError(_('Select the animal group that was fed.'))
            if rec.allocation_type == 'animal' and not rec.animal_id:
                raise ValidationError(_('Select the animal that was fed.'))

    @api.constrains('uom_id', 'product_id')
    def _check_uom(self):
        for rec in self:
            if rec.uom_id.category_id != rec.product_id.uom_id.category_id:
                raise ValidationError(_('The unit must be compatible with the unit of %s.', rec.product_id.display_name))

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.feed.consumption') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        allowed = {'correction_reason', 'notes', 'state', 'reversal_move_id', 'message_main_attachment_id'}
        if set(vals) - allowed and any(rec.state != 'draft' for rec in self):
            raise UserError(_('Posted feed records cannot be modified; reverse them with a reason instead.'))
        return super().write(vals)

    def unlink(self):
        if any(rec.state not in ('draft', 'cancelled') or rec.move_id for rec in self):
            raise UserError(_('Posted feed records cannot be deleted; reverse them instead.'))
        return super().unlink()

    # ------------------------------------------------------------------
    def _lock_for_posting(self):
        """Row-lock the records so concurrent clicks cannot post twice."""
        self.flush_recordset()
        self.env.cr.execute(
            'SELECT id FROM dairy_feed_consumption WHERE id IN %s FOR UPDATE NOWAIT', [tuple(self.ids)])
        self.invalidate_recordset(['state', 'move_id'])

    def action_validate(self):
        self._lock_for_posting()
        for rec in self:
            if rec.state != 'draft' or rec.move_id:
                raise UserError(_('%s has already been posted.', rec.name))
            if not (rec.location_id and rec.location_dest_id):
                rec.company_id._dairy_feed_locations()
            if rec.location_id.usage != 'internal':
                raise UserError(_('Feed must be issued from an internal stock location.'))
            if rec.product_id.tracking != 'none' and not rec.lot_id:
                raise UserError(_('Select the lot of %s that was issued.', rec.product_id.display_name))
            check_valuation_config(self.env, rec.product_id, rec.company_id, rec.location_dest_id)
            check_available(self.env, rec.product_id, rec.actual_qty, rec.uom_id, rec.location_id, rec.lot_id)
            if rec.consumption_type == 'feeding':
                animals = rec.animal_id if rec.allocation_type == 'animal' else rec.group_id.animal_ids.filtered(
                    lambda a: a.active_status == 'active')
                if not animals:
                    raise UserError(_('%s has no active animals to allocate the feed to.', rec.group_id.display_name))
            else:
                animals = self.env['dairy.animal']
            move = post_stock_move(
                self.env, rec.product_id, rec.actual_qty, rec.uom_id, rec.location_id, rec.location_dest_id,
                rec.company_id, name=_('Feed: %s', rec.product_id.display_name), origin=rec.name, lot=rec.lot_id)
            super(DairyFeedConsumption, rec).write({
                'state': 'done',
                'move_id': move.id,
                'product_qty': move.product_qty,
                'cost_amount': move_cost(move),
                'allocated_animal_ids': [(6, 0, animals.ids)],
                'head_count': len(animals),
            })
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft records can be cancelled; reverse posted records.'))
        self.write({'state': 'cancelled'})

    def action_reverse(self):
        """Return the issued quantity to stock, documenting the reason."""
        self._lock_for_posting()
        for rec in self:
            if rec.state != 'done' or rec.reversal_move_id:
                raise UserError(_('Only posted, non-reversed records can be reversed.'))
            if not rec.correction_reason:
                raise UserError(_('Enter a correction reason on %s before reversing it.', rec.name))
            move = rec.move_id
            reversal = post_stock_move(
                self.env, move.product_id, move.quantity, move.product_uom, move.location_dest_id, move.location_id,
                rec.company_id, name=_('Reversal: %s', move.name), origin=_('%s (reversal)', rec.name),
                lot=move.move_line_ids[:1].lot_id, extra_vals={'origin_returned_move_id': move.id})
            rec.write({'state': 'reversed', 'reversal_move_id': reversal.id})
            rec.message_post(body=_('Reversed: %s', rec.correction_reason))
        return True

    def action_view_move(self):
        self.ensure_one()
        moves = self.move_id | self.reversal_move_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Moves'),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .stock_utils import check_available, check_valuation_config, move_cost, post_stock_move

ROUTES = [
    ('im', 'Intramuscular'),
    ('iv', 'Intravenous'),
    ('sc', 'Subcutaneous'),
    ('oral', 'Oral'),
    ('intramammary', 'Intramammary'),
    ('topical', 'Topical'),
    ('intrauterine', 'Intrauterine'),
    ('other', 'Other'),
]


class DairyMedicineIssueMixin(models.AbstractModel):
    """Common medicine issue (stock) and milk-withdrawal logic for treatments and vaccinations."""
    _name = 'dairy.medicine.issue.mixin'
    _description = 'Dairy Medicine Issue'

    def _issue_medicine(self, product, quantity, uom, lot, origin):
        """Post the medicine issue; returns (move, cost). Nothing is posted for zero quantity."""
        self.ensure_one()
        if not product or not product.is_storable:
            return self.env['stock.move'], 0.0
        if quantity <= 0:
            raise UserError(_('Enter the quantity of %s taken from stock.', product.display_name))
        source, destination = self.company_id._dairy_medicine_locations()
        if product.tracking != 'none' and not lot:
            raise UserError(_('Select the lot/batch of %s that was used.', product.display_name))
        if lot and lot.product_id != product:
            raise UserError(_('Lot %(lot)s does not belong to %(product)s.', lot=lot.name, product=product.display_name))
        if lot and lot.expiration_date and lot.expiration_date.date() < self._issue_date():
            raise UserError(_('Lot %(lot)s of %(product)s expired on %(date)s.', lot=lot.name,
                              product=product.display_name, date=lot.expiration_date.date()))
        check_valuation_config(self.env, product, self.company_id, destination)
        check_available(self.env, product, quantity, uom, source, lot)
        move = post_stock_move(self.env, product, quantity, uom, source, destination, self.company_id,
                               name=_('Medicine: %s', product.display_name), origin=origin, lot=lot)
        return move, move_cost(move)

    def _create_withdrawal(self, animal, start, end, reason):
        self.ensure_one()
        return self.env['dairy.milk.withdrawal'].create({
            'animal_id': animal.id,
            'start_date': start,
            'end_date': end,
            'reason': reason,
            'origin': self.name,
            'source_model': self._name,
            'source_res_id': self.id,
            'company_id': self.company_id.id,
        })

    def _check_animal_treatable(self, animal):
        if animal.active_status != 'active':
            raise UserError(_('%s is no longer in the herd.', animal.display_name))

    def _lock_rows(self):
        if not self:
            return
        self.flush_recordset()
        self.env.cr.execute(f'SELECT id FROM "{self._table}" WHERE id IN %s FOR UPDATE NOWAIT', [tuple(self.ids)])
        self.invalidate_recordset()


class DairyTreatment(models.Model):
    _name = 'dairy.treatment'
    _description = 'Veterinary Treatment'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.medicine.issue.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    case_id = fields.Many2one('dairy.health.case', string='Health Case', required=True, index=True,
                              ondelete='restrict', check_company=True,
                              domain="[('state', 'not in', ('closed', 'cancelled'))]")
    animal_id = fields.Many2one(related='case_id.animal_id', store=True, index=True)
    product_id = fields.Many2one('product.product', string='Medicine', check_company=True,
                                 domain="[('is_dairy_medicine', '=', True)]", tracking=True)
    description = fields.Char(string='Treatment', help='Procedure or non-stock treatment description.')
    dosage = fields.Char(help='Prescribed dose, e.g. "20 ml every 24 h".')
    route = fields.Selection(ROUTES, compute='_compute_from_product', store=True, readonly=False)
    duration_days = fields.Integer(string='Duration (days)', default=1)
    start_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    end_date = fields.Date(compute='_compute_end_date', store=True, readonly=False, tracking=True)
    quantity = fields.Float(string='Quantity Issued', digits='Product Unit of Measure',
                            help='Total quantity taken from stock for the full course.')
    uom_id = fields.Many2one('uom.uom', string='Unit', compute='_compute_from_product', store=True, readonly=False)
    uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    lot_id = fields.Many2one('stock.lot', string='Lot / Batch', check_company=True,
                             domain="[('product_id', '=', product_id)]")
    tracking = fields.Selection(related='product_id.tracking')
    milk_withdrawal_days = fields.Integer(compute='_compute_from_product', store=True, readonly=False,
                                          tracking=True)
    withdrawal_end_date = fields.Date(compute='_compute_withdrawal_end_date', store=True,
                                      string='Milk Withdrawal Until')
    withdrawal_instructions = fields.Text()
    withdrawal_id = fields.Many2one('dairy.milk.withdrawal', readonly=True, copy=False)
    administered_by_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    veterinarian_id = fields.Many2one(related='case_id.veterinarian_id')
    move_id = fields.Many2one('stock.move', readonly=True, copy=False)
    reversal_move_id = fields.Many2one('stock.move', readonly=True, copy=False)
    cost_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Prescribed'),
        ('administered', 'Administered'),
        ('reversed', 'Reversed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True, index=True)
    reversal_reason = fields.Text(copy=False)
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('quantity_positive', 'CHECK(quantity >= 0)', 'The issued quantity cannot be negative.'),
        ('duration_positive', 'CHECK(duration_days >= 1)', 'The duration must be at least one day.'),
        ('withdrawal_positive', 'CHECK(milk_withdrawal_days >= 0)', 'The withdrawal period cannot be negative.'),
        ('move_uniq', 'unique(move_id)', 'A stock move can only be linked to one treatment.'),
    ]

    @api.depends('product_id')
    def _compute_from_product(self):
        for treatment in self:
            product = treatment.product_id
            if product:
                treatment.route = product.dairy_default_route or treatment.route
                treatment.uom_id = product.uom_id
                treatment.milk_withdrawal_days = product.dairy_milk_withdrawal_days

    @api.depends('start_date', 'duration_days')
    def _compute_end_date(self):
        for treatment in self:
            if treatment.start_date:
                treatment.end_date = treatment.start_date + timedelta(days=max(treatment.duration_days, 1) - 1)

    @api.depends('end_date', 'milk_withdrawal_days')
    def _compute_withdrawal_end_date(self):
        for treatment in self:
            if treatment.end_date and treatment.milk_withdrawal_days:
                treatment.withdrawal_end_date = treatment.end_date + timedelta(days=treatment.milk_withdrawal_days)
            else:
                treatment.withdrawal_end_date = False

    @api.constrains('start_date', 'end_date', 'product_id', 'description', 'uom_id')
    def _check_values(self):
        for treatment in self:
            if treatment.end_date and treatment.end_date < treatment.start_date:
                raise ValidationError(_('The treatment cannot end before it starts.'))
            if not (treatment.product_id or treatment.description):
                raise ValidationError(_('Select a medicine or describe the treatment.'))
            if treatment.product_id and treatment.uom_id and \
                    treatment.uom_id.category_id != treatment.product_id.uom_id.category_id:
                raise ValidationError(_('Incompatible unit for %s.', treatment.product_id.display_name))

    def _issue_date(self):
        return self.start_date

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.treatment') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        allowed = {'notes', 'state', 'reversal_reason', 'reversal_move_id', 'withdrawal_instructions'}
        if set(vals) - allowed and any(t.state != 'draft' for t in self):
            raise UserError(_('Administered treatments cannot be modified; reverse them with a reason.'))
        return super().write(vals)

    def unlink(self):
        if any(t.state != 'draft' or t.move_id for t in self):
            raise UserError(_('Only prescribed (not administered) treatments can be deleted.'))
        return super().unlink()

    def action_administer(self):
        self._lock_rows()
        for treatment in self:
            if treatment.state != 'draft' or treatment.move_id:
                raise UserError(_('%s has already been administered.', treatment.name))
            if treatment.case_id.state in ('closed', 'cancelled'):
                raise UserError(_('The health case %s is closed.', treatment.case_id.name))
            if treatment.start_date > fields.Date.context_today(treatment):
                raise UserError(_('A treatment cannot be administered in the future.'))
            treatment._check_animal_treatable(treatment.animal_id)
            move, cost = treatment._issue_medicine(treatment.product_id, treatment.quantity, treatment.uom_id,
                                                   treatment.lot_id, treatment.name)
            vals = {'state': 'administered', 'move_id': move.id, 'cost_amount': cost}
            if treatment.withdrawal_end_date:
                vals['withdrawal_id'] = treatment._create_withdrawal(
                    treatment.animal_id, treatment.start_date, treatment.withdrawal_end_date,
                    _('%(med)s (%(case)s)', med=treatment.product_id.display_name or treatment.description,
                      case=treatment.case_id.name)).id
            super(DairyTreatment, treatment).write(vals)
            if treatment.case_id.state in ('reported', 'diagnosed'):
                treatment.case_id.state = 'treatment'
        return True

    def action_cancel(self):
        for treatment in self:
            if treatment.state != 'draft':
                raise UserError(_('Administered treatments must be reversed, not cancelled.'))
        self.write({'state': 'cancelled'})

    def action_reverse(self):
        """Undo a treatment recorded in error: return medicine to stock and cancel its restriction."""
        if not self.env.user.has_group('dairy_farm_core.group_dairy_veterinarian'):
            raise AccessError(_('Only veterinarians can reverse treatments.'))
        self._lock_rows()
        for treatment in self:
            if treatment.state != 'administered':
                raise UserError(_('Only administered treatments can be reversed.'))
            if not treatment.reversal_reason:
                raise UserError(_('Enter the reason for reversing %s.', treatment.name))
            vals = {'state': 'reversed'}
            move = treatment.move_id
            if move:
                vals['reversal_move_id'] = post_stock_move(
                    self.env, move.product_id, move.quantity, move.product_uom, move.location_dest_id,
                    move.location_id, treatment.company_id, name=_('Reversal: %s', move.name),
                    origin=_('%s (reversal)', treatment.name), lot=move.move_line_ids[:1].lot_id,
                    extra_vals={'origin_returned_move_id': move.id}).id
            if treatment.withdrawal_id.state == 'active':
                treatment.withdrawal_id.write({'cancel_reason': _('Treatment %(ref)s reversed: %(reason)s',
                                                                  ref=treatment.name, reason=treatment.reversal_reason)})
                treatment.withdrawal_id.action_cancel()
            treatment.write(vals)
        return True

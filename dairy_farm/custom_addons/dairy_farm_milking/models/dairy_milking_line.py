from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MAX_LITERS_PER_MILKING = 40.0

ENTRY_STATUS = [
    ('pending', 'Not Entered'),
    ('recorded', 'Milked'),
    ('zero', 'Zero Yield'),
    ('missed', 'Missed Milking'),
]

# fields recomputed by the system (restriction changes) on locked sessions
DESTINATION_FIELDS = {'milk_destination', 'restriction_id'}


class DairyMilkingLine(models.Model):
    _name = 'dairy.milking.line'
    _description = 'Cow-wise Milking Record'
    _order = 'date desc, shift_sequence, animal_tag'
    _check_company_auto = True

    session_id = fields.Many2one('dairy.milking.session', required=True, ondelete='cascade', index=True)
    animal_id = fields.Many2one('dairy.animal', required=True, ondelete='restrict', index=True,
                                check_company=True)
    animal_tag = fields.Char(related='animal_id.tag_number', store=True, string='Tag')
    date = fields.Date(related='session_id.date', store=True, index=True)
    shift_id = fields.Many2one(related='session_id.shift_id', store=True)
    shift_sequence = fields.Integer(related='session_id.shift_sequence', store=True)
    session_state = fields.Selection(related='session_id.state', store=True, string='Session Status')
    company_id = fields.Many2one(related='session_id.company_id', store=True, index=True)
    group_id = fields.Many2one('dairy.animal.group', string='Group at Milking', readonly=True,
                               help='Animal group when the record was created (kept for historical reporting).')
    breed_id = fields.Many2one(related='animal_id.breed_id', store=True)

    entry_status = fields.Selection(ENTRY_STATUS, required=True, default='pending', index=True)
    quantity_liters = fields.Float(string='Liters', digits=(16, 2), default=0.0)
    quality_status = fields.Selection([
        ('normal', 'Normal'),
        ('abnormal', 'Abnormal (discard)'),
        ('colostrum', 'Colostrum (discard)'),
    ], default='normal', required=True)
    milk_destination = fields.Selection([
        ('saleable', 'Saleable'),
        ('withheld', 'Withheld (withdrawal)'),
        ('discarded', 'Discarded (quality)'),
        ('none', 'No Milk'),
    ], readonly=True, default='none', index=True)
    restriction_id = fields.Many2one('dairy.milk.withdrawal', readonly=True, string='Restriction')
    remarks = fields.Char()
    recorded_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    recorded_at = fields.Datetime(default=fields.Datetime.now, readonly=True)

    _sql_constraints = [
        ('animal_session_uniq', 'unique(session_id, animal_id)',
         'Each animal can only appear once per milking session.'),
        ('quantity_positive', 'CHECK(quantity_liters >= 0)', 'Milk quantity cannot be negative.'),
        ('quantity_status_consistent', "CHECK(entry_status = 'recorded' OR quantity_liters = 0)",
         'Only "Milked" entries can carry a quantity; use "Milked" with the quantity or record zero/missed.'),
    ]

    # ------------------------------------------------------------------
    @api.constrains('quantity_liters', 'entry_status')
    def _check_quantity(self):
        for line in self:
            if line.entry_status == 'recorded' and line.quantity_liters <= 0:
                raise ValidationError(_('%s: a milked entry needs a quantity greater than zero '
                                        '(use "Zero Yield" for no milk).', line.animal_id.display_name))
            if line.quantity_liters > MAX_LITERS_PER_MILKING:
                raise ValidationError(_('%(animal)s: %(qty)s L in one milking is not plausible.',
                                        animal=line.animal_id.display_name, qty=line.quantity_liters))

    @api.constrains('animal_id', 'entry_status')
    def _check_eligibility(self):
        for line in self:
            # eligibility is assessed at data-entry time; historical corrections
            # of confirmed sessions are not re-validated against today's status
            if line.session_id.state != 'draft' or line.entry_status not in ('recorded', 'zero'):
                continue
            if not line.animal_id._is_milking_eligible():
                raise ValidationError(_(
                    '%s is not eligible for milking (must be an active, lactating female). '
                    'Record it as "Missed Milking" with a remark if it was presented.',
                    line.animal_id.display_name))

    # ------------------------------------------------------------------
    @api.onchange('quantity_liters')
    def _onchange_quantity(self):
        if self.quantity_liters > 0:
            self.entry_status = 'recorded'

    @api.onchange('entry_status')
    def _onchange_entry_status(self):
        if self.entry_status != 'recorded':
            self.quantity_liters = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        sessions = self.env['dairy.milking.session'].browse([v['session_id'] for v in vals_list if v.get('session_id')])
        if any(s.state != 'draft' for s in sessions) and not self._is_authorised_correction():
            raise UserError(_('Cow records can only be added to draft sessions.'))
        for vals in vals_list:
            if vals.get('quantity_liters', 0) > 0 and 'entry_status' not in vals:
                vals['entry_status'] = 'recorded'
            if vals.get('animal_id') and 'group_id' not in vals:
                vals['group_id'] = self.env['dairy.animal'].browse(vals['animal_id']).group_id.id
        lines = super().create(vals_list)
        lines._update_milk_destination()
        return lines

    def write(self, vals):
        system_update = self.env.context.get('dairy_destination_update') and set(vals) <= DESTINATION_FIELDS
        if not system_update and any(l.session_id.state != 'draft' for l in self):
            if not self._is_authorised_correction():
                raise UserError(_('Cow records of submitted, confirmed or cancelled sessions cannot be '
                                  'edited directly. Use a correction request.'))
        if not system_update and ({'quantity_liters', 'entry_status'} & set(vals)):
            if vals.get('quantity_liters', 0) > 0 and 'entry_status' not in vals:
                vals['entry_status'] = 'recorded'
            vals.setdefault('recorded_by', self.env.uid)
            vals.setdefault('recorded_at', fields.Datetime.now())
        res = super().write(vals)
        if {'animal_id', 'quality_status', 'quantity_liters', 'entry_status'} & set(vals):
            self._update_milk_destination()
        return res

    def unlink(self):
        if any(l.session_id.state != 'draft' for l in self):
            raise UserError(_('Cow records can only be removed from draft sessions.'))
        return super().unlink()

    def _is_authorised_correction(self):
        if not self.env.context.get('dairy_milking_correction'):
            return False
        if not self.env.user.has_group('dairy_farm_core.group_dairy_manager'):
            raise AccessError(_('Only a Dairy Farm Manager can apply milking corrections.'))
        return True

    # ------------------------------------------------------------------
    def _update_milk_destination(self):
        """Classify each record's milk as saleable, withheld or discarded.

        Withdrawal restrictions are created by veterinarians who have no write
        access to milking records, so the reclassification (only these two
        derived fields) is performed with elevated rights.
        """
        Withdrawal = self.env['dairy.milk.withdrawal'].sudo()
        for line in self.sudo():
            restriction = Withdrawal.search(
                [('animal_id', '=', line.animal_id.id)] + Withdrawal._restriction_domain(line.date),
                limit=1)
            if line.entry_status != 'recorded':
                destination = 'none'
            elif restriction:
                destination = 'withheld'
            elif line.quality_status != 'normal':
                destination = 'discarded'
            else:
                destination = 'saleable'
            if line.milk_destination != destination or line.restriction_id != restriction:
                line.with_context(dairy_destination_update=True).write({
                    'milk_destination': destination,
                    'restriction_id': restriction.id,
                })

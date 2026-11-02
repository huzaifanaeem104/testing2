from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DairyCalvingEvent(models.Model):
    _name = 'dairy.calving.event'
    _description = 'Calving Event'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'calving_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    dam_id = fields.Many2one('dairy.animal', string='Dam', required=True, index=True, ondelete='restrict',
                             domain="[('gender', '=', 'female'), ('active_status', '=', 'active')]",
                             check_company=True, tracking=True)
    breeding_event_id = fields.Many2one('dairy.breeding.event', string='Breeding Event', check_company=True,
                                        domain="[('animal_id', '=', dam_id), ('event_type', '=', 'breeding'), ('state', '=', 'done')]")
    sire_id = fields.Many2one('dairy.animal', string='Sire', domain="[('gender', '=', 'male')]",
                              compute='_compute_sire', store=True, readonly=False, check_company=True)
    sire_reference = fields.Char(compute='_compute_sire', store=True, readonly=False)
    calving_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    calving_ease = fields.Selection([
        ('normal', 'Normal / Unassisted'),
        ('assisted', 'Assisted'),
        ('difficult', 'Difficult (dystocia)'),
        ('caesarean', 'Caesarean'),
    ], default='normal', required=True)
    outcome = fields.Selection([
        ('live', 'Live Birth'),
        ('stillbirth', 'Stillbirth'),
        ('abortion', 'Abortion / Miscarriage'),
    ], default='live', required=True, tracking=True)
    start_lactation = fields.Boolean(default=True, help='Start a new lactation for the dam.')
    calf_line_ids = fields.One2many('dairy.calving.calf', 'calving_id', string='Calves', copy=False)
    calf_count = fields.Integer(compute='_compute_calf_count')
    complications = fields.Text()
    veterinarian_id = fields.Many2one('res.partner', string='Veterinarian')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    @api.depends('breeding_event_id')
    def _compute_sire(self):
        for calving in self:
            if calving.breeding_event_id:
                calving.sire_id = calving.breeding_event_id.sire_id
                calving.sire_reference = calving.breeding_event_id.semen_reference

    def _compute_calf_count(self):
        for calving in self:
            calving.calf_count = len(calving.calf_line_ids.calf_id)

    @api.onchange('outcome')
    def _onchange_outcome(self):
        self.start_lactation = self.outcome != 'abortion'

    @api.constrains('calving_date', 'dam_id', 'breeding_event_id')
    def _check_dates(self):
        for calving in self:
            if calving.calving_date > fields.Date.context_today(calving):
                raise ValidationError(_('The calving date cannot be in the future.'))
            if calving.breeding_event_id and calving.breeding_event_id.breeding_date >= calving.calving_date:
                raise ValidationError(_('Calving must follow the breeding date.'))
            if calving.breeding_event_id.animal_id and calving.breeding_event_id.animal_id != calving.dam_id:
                raise ValidationError(_('The breeding event belongs to another animal.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.calving.event') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(c.state == 'done' for c in self):
            raise UserError(_('Completed calvings are part of the herd history.'))
        return super().unlink()

    def action_done(self):
        Animal = self.env['dairy.animal']
        for calving in self:
            if calving.state != 'draft':
                raise UserError(_('%s is already completed.', calving.name))
            if calving.outcome == 'live' and not calving.calf_line_ids.filtered(lambda l: l.status == 'alive'):
                raise UserError(_('Register at least one live calf for a live birth.'))
            dam = calving.dam_id
            for line in calving.calf_line_ids.filtered(lambda l: l.status == 'alive' and not l.calf_id):
                if not line.tag_number:
                    raise UserError(_('Every live calf needs a tag number.'))
                line.calf_id = Animal.create({
                    'tag_number': line.tag_number,
                    'nickname': line.nickname,
                    'animal_type': 'calf',
                    'gender': line.gender,
                    'birth_date': calving.calving_date,
                    'acquisition_type': 'born',
                    'dam_id': dam.id,
                    'sire_id': calving.sire_id.id,
                    'sire_reference': calving.sire_reference,
                    'breed_id': dam.breed_id.id,
                    'location_id': dam.location_id.id,
                    'weight_kg': line.birth_weight,
                    'company_id': calving.company_id.id,
                    'production_status': 'growing',
                })
            dam_vals = {'reproductive_status': 'open', 'expected_calving_date': False}
            if calving.start_lactation:
                dam_vals.update({
                    'production_status': 'lactating',
                    'lactation_number': dam.lactation_number + 1,
                    'last_calving_date': calving.calving_date,
                    'animal_type': 'cow' if dam.animal_type == 'heifer' else dam.animal_type,
                })
            dam.write(dam_vals)
            if calving.breeding_event_id:
                calving.breeding_event_id.result = 'lost' if calving.outcome == 'abortion' else 'calved'
            calving.state = 'done'
            self.env['dairy.alert.mixin']._dairy_clear_alerts(dam, _('Expected calving'))
            self.env['dairy.alert.mixin']._dairy_clear_alerts(dam, _('Dry-off due'))
            dam.message_post(body=_('Calving %(ref)s recorded: %(outcome)s, %(n)s calf/calves registered.',
                                    ref=calving.name, outcome=dict(self._fields['outcome'].selection)[calving.outcome],
                                    n=len(calving.calf_line_ids.calf_id)))
        return True

    def action_cancel(self):
        if any(c.state == 'done' for c in self):
            raise UserError(_('Completed calvings cannot be cancelled.'))
        self.write({'state': 'cancelled'})

    def action_view_calves(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_core.action_dairy_animal')
        action['domain'] = [('id', 'in', self.calf_line_ids.calf_id.ids)]
        action['context'] = {}
        return action


class DairyCalvingCalf(models.Model):
    _name = 'dairy.calving.calf'
    _description = 'Calf Born'

    calving_id = fields.Many2one('dairy.calving.event', required=True, ondelete='cascade', index=True)
    tag_number = fields.Char(string='Tag / RFID')
    nickname = fields.Char(string='Name')
    gender = fields.Selection([('female', 'Female'), ('male', 'Male')], required=True, default='female')
    birth_weight = fields.Float(string='Birth Weight (kg)')
    status = fields.Selection([('alive', 'Alive'), ('dead', 'Stillborn / Died')], required=True, default='alive')
    calf_id = fields.Many2one('dairy.animal', string='Registered Animal', readonly=True, ondelete='restrict')
    notes = fields.Char()

    _sql_constraints = [
        ('weight_positive', 'CHECK(birth_weight >= 0)', 'Birth weight cannot be negative.'),
    ]

    def write(self, vals):
        if any(l.calving_id.state == 'done' for l in self) and set(vals) - {'notes'}:
            raise UserError(_('Calves of a completed calving cannot be changed; edit the animal record instead.'))
        return super().write(vals)

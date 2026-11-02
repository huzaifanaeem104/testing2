from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DairyBreedingEvent(models.Model):
    """Heat observation or service (AI / natural / embryo transfer) of a female."""
    _name = 'dairy.breeding.event'
    _description = 'Breeding Event'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.alert.mixin']
    _order = 'event_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    animal_id = fields.Many2one('dairy.animal', required=True, index=True, ondelete='restrict', tracking=True,
                                domain="[('gender', '=', 'female'), ('active_status', '=', 'active')]",
                                check_company=True)
    event_type = fields.Selection([
        ('heat', 'Heat Detection'),
        ('breeding', 'Insemination / Service'),
    ], required=True, default='breeding', tracking=True, index=True)
    heat_date = fields.Date(string='Heat Detected On', tracking=True, default=fields.Date.context_today)
    heat_signs = fields.Selection([
        ('standing', 'Standing to be mounted'),
        ('mucus', 'Clear mucus discharge'),
        ('restless', 'Restlessness / mounting others'),
        ('drop', 'Milk drop'),
        ('activity', 'Activity monitor alert'),
        ('other', 'Other'),
    ])
    heat_event_id = fields.Many2one('dairy.breeding.event', string='Related Heat', check_company=True,
                                    domain="[('animal_id', '=', animal_id), ('event_type', '=', 'heat')]")
    breeding_date = fields.Date(string='Service Date', tracking=True, default=fields.Date.context_today)
    event_date = fields.Date(compute='_compute_event_date', store=True, index=True)
    method = fields.Selection([
        ('ai', 'Artificial Insemination'),
        ('natural', 'Natural Service'),
        ('et', 'Embryo Transfer'),
    ], tracking=True)
    sire_id = fields.Many2one('dairy.animal', string='Bull', domain="[('gender', '=', 'male')]",
                              check_company=True, ondelete='restrict')
    semen_reference = fields.Char(string='Semen / Straw Reference')
    technician_id = fields.Many2one('res.partner', string='Technician / Inseminator')
    service_number = fields.Integer(readonly=True, help='Service count in the current reproductive cycle.')
    pregnancy_check_due = fields.Date(compute='_compute_pregnancy_check_due', store=True)
    pregnancy_check_ids = fields.One2many('dairy.pregnancy.check', 'breeding_event_id', string='Pregnancy Checks')
    result = fields.Selection([
        ('pending', 'Awaiting Check'),
        ('pregnant', 'Pregnant'),
        ('open', 'Not Pregnant'),
        ('lost', 'Pregnancy Lost'),
        ('calved', 'Calved'),
    ], readonly=True, copy=False, tracking=True, index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Recorded'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    @api.depends('event_type', 'heat_date', 'breeding_date')
    def _compute_event_date(self):
        for event in self:
            event.event_date = event.breeding_date if event.event_type == 'breeding' else event.heat_date

    @api.depends('breeding_date', 'event_type', 'company_id.dairy_pregnancy_check_days')
    def _compute_pregnancy_check_due(self):
        for event in self:
            if event.event_type == 'breeding' and event.breeding_date:
                event.pregnancy_check_due = event.breeding_date + timedelta(
                    days=event.company_id.dairy_pregnancy_check_days or 35)
            else:
                event.pregnancy_check_due = False

    @api.constrains('event_type', 'heat_date', 'breeding_date', 'method')
    def _check_dates(self):
        today = fields.Date.context_today(self)
        for event in self:
            if event.event_type == 'heat' and not event.heat_date:
                raise ValidationError(_('Enter the date the heat was detected.'))
            if event.event_type == 'breeding' and not (event.breeding_date and event.method):
                raise ValidationError(_('Enter the service date and the breeding method.'))
            for date in (event.heat_date, event.breeding_date):
                if date and date > today:
                    raise ValidationError(_('Breeding events cannot be recorded in the future.'))
                if date and event.animal_id.birth_date and date < event.animal_id.birth_date:
                    raise ValidationError(_('The event date is before the birth of %s.', event.animal_id.display_name))

    @api.constrains('animal_id', 'sire_id')
    def _check_animals(self):
        for event in self:
            if event.animal_id.gender != 'female':
                raise ValidationError(_('Only female animals can be bred.'))
            if event.sire_id and event.sire_id.gender != 'male':
                raise ValidationError(_('The bull must be male.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.breeding.event') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(e.state == 'done' for e in self):
            raise UserError(_('Recorded breeding events are part of the reproductive history; cancel them instead.'))
        return super().unlink()

    def action_done(self):
        for event in self:
            if event.state != 'draft':
                raise UserError(_('%s is already recorded.', event.name))
            animal = event.animal_id
            if animal.active_status != 'active':
                raise UserError(_('%s is not an active animal.', animal.display_name))
            if event.event_type == 'breeding':
                if animal.reproductive_status == 'pregnant':
                    raise UserError(_('%s is confirmed pregnant; record a pregnancy check showing she is open '
                                      'before a new service.', animal.display_name))
                cycle_start = animal.last_calving_date or animal.birth_date or fields.Date.to_date('1900-01-01')
                previous = self.search_count([
                    ('animal_id', '=', animal.id), ('event_type', '=', 'breeding'), ('state', '=', 'done'),
                    ('breeding_date', '>=', cycle_start), ('id', '!=', event.id)])
                event.write({'state': 'done', 'result': 'pending', 'service_number': previous + 1})
                # breeding alone never makes the cow pregnant
                animal.write({'reproductive_status': 'inseminated', 'last_breeding_date': event.breeding_date})
                event._dairy_schedule_alert(
                    event._check_due_summary(), date_deadline=event.pregnancy_check_due,
                    note=_('Pregnancy examination due for %s.', animal.display_name))
            else:
                event.write({'state': 'done'})
                animal.write({'last_heat_date': event.heat_date})
        return True

    def action_cancel(self):
        for event in self:
            if event.pregnancy_check_ids.filtered(lambda c: c.state == 'done'):
                raise UserError(_('%s has recorded pregnancy checks and cannot be cancelled.', event.name))
        self.write({'state': 'cancelled', 'result': False})
        for event in self.filtered(lambda e: e.event_type == 'breeding'):
            event.animal_id._recompute_reproductive_status()
        return True

    def action_create_pregnancy_check(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pregnancy Check'),
            'res_model': 'dairy.pregnancy.check',
            'view_mode': 'form',
            'context': {'default_breeding_event_id': self.id, 'default_animal_id': self.animal_id.id},
        }

    def action_create_breeding_from_heat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Insemination'),
            'res_model': 'dairy.breeding.event',
            'view_mode': 'form',
            'context': {'default_animal_id': self.animal_id.id, 'default_event_type': 'breeding',
                        'default_heat_event_id': self.id, 'default_breeding_date': fields.Date.context_today(self),
                        'default_method': 'ai'},
        }

    def _check_due_summary(self):
        return _('Pregnancy check due')

    @api.depends('name', 'animal_id', 'event_date')
    def _compute_display_name(self):
        for event in self:
            event.display_name = f'{event.name} - {event.animal_id.display_name or ""} ({event.event_date or ""})'

    @api.model
    def _cron_breeding_alerts(self):
        """Pregnancy checks due/overdue, upcoming calvings and dry-off reminders (idempotent)."""
        today = fields.Date.context_today(self)
        due = self.search([('state', '=', 'done'), ('event_type', '=', 'breeding'), ('result', '=', 'pending'),
                           ('pregnancy_check_due', '<=', today)])
        for event in due:
            event._dairy_schedule_alert(event._check_due_summary(), date_deadline=event.pregnancy_check_due)
        Animal = self.env['dairy.animal']
        for company in self.env['res.company'].search([]):
            window = today + timedelta(days=company.dairy_calving_alert_days or 21)
            for animal in Animal.search([('company_id', '=', company.id), ('reproductive_status', '=', 'pregnant'),
                                         ('expected_calving_date', '<=', window)]):
                animal._dairy_schedule_alert(
                    _('Expected calving'), date_deadline=animal.expected_calving_date,
                    note=_('%(animal)s is expected to calve on %(date)s.',
                           animal=animal.display_name, date=animal.expected_calving_date))
            dry_days = company.dairy_dry_off_days or 60
            for animal in Animal.search([('company_id', '=', company.id), ('reproductive_status', '=', 'pregnant'),
                                         ('production_status', '=', 'lactating'),
                                         ('expected_calving_date', '<=', today + timedelta(days=dry_days))]):
                animal._dairy_schedule_alert(
                    _('Dry-off due'), date_deadline=animal.expected_calving_date - timedelta(days=dry_days))

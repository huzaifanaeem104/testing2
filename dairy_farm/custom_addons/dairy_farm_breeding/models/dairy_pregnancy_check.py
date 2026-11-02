from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DairyPregnancyCheck(models.Model):
    _name = 'dairy.pregnancy.check'
    _description = 'Pregnancy Examination'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    animal_id = fields.Many2one('dairy.animal', required=True, index=True, ondelete='restrict', tracking=True,
                                domain="[('gender', '=', 'female')]", check_company=True)
    breeding_event_id = fields.Many2one('dairy.breeding.event', string='Breeding Event', required=True,
                                        index=True, check_company=True, ondelete='restrict',
                                        domain="[('animal_id', '=', animal_id), ('event_type', '=', 'breeding'), ('state', '=', 'done')]")
    breeding_date = fields.Date(related='breeding_event_id.breeding_date')
    date = fields.Date(string='Examination Date', required=True, default=fields.Date.context_today, tracking=True)
    days_after_service = fields.Integer(compute='_compute_days_after_service')
    method = fields.Selection([
        ('palpation', 'Rectal Palpation'),
        ('ultrasound', 'Ultrasound'),
        ('blood', 'Blood / Milk Test'),
        ('other', 'Other'),
    ], default='ultrasound', required=True)
    result = fields.Selection([
        ('pregnant', 'Pregnant'),
        ('open', 'Not Pregnant'),
        ('inconclusive', 'Inconclusive'),
    ], tracking=True)
    expected_calving_date = fields.Date(compute='_compute_expected_calving_date', store=True, readonly=False,
                                        tracking=True)
    veterinarian_id = fields.Many2one('res.partner', string='Veterinarian')
    state = fields.Selection([
        ('draft', 'Scheduled'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    @api.depends('date', 'breeding_date')
    def _compute_days_after_service(self):
        for check in self:
            check.days_after_service = (check.date - check.breeding_date).days if check.date and check.breeding_date else 0

    @api.depends('result', 'breeding_event_id.breeding_date', 'company_id.dairy_gestation_days')
    def _compute_expected_calving_date(self):
        for check in self:
            if check.result == 'pregnant' and check.breeding_event_id.breeding_date:
                check.expected_calving_date = check.breeding_event_id.breeding_date + timedelta(
                    days=check.company_id.dairy_gestation_days or 283)
            else:
                check.expected_calving_date = False

    @api.constrains('date', 'breeding_event_id', 'animal_id')
    def _check_consistency(self):
        for check in self:
            if check.breeding_event_id.animal_id != check.animal_id:
                raise ValidationError(_('The breeding event belongs to another animal.'))
            if check.breeding_date and check.date < check.breeding_date:
                raise ValidationError(_('The examination cannot precede the service date.'))
            if check.date > fields.Date.context_today(check) and check.state == 'done':
                raise ValidationError(_('A completed examination cannot be dated in the future.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.pregnancy.check') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if any(c.state == 'done' for c in self) and set(vals) - {'notes', 'state'}:
            raise UserError(_('Completed pregnancy checks cannot be modified; record a new examination.'))
        return super().write(vals)

    def unlink(self):
        if any(c.state == 'done' for c in self):
            raise UserError(_('Completed pregnancy checks are part of the clinical history.'))
        return super().unlink()

    def action_done(self):
        for check in self:
            if check.state != 'draft':
                raise UserError(_('%s is already completed.', check.name))
            if not check.result:
                raise UserError(_('Record the examination result.'))
            if check.date > fields.Date.context_today(check):
                raise UserError(_('The examination date is in the future.'))
            event = check.breeding_event_id
            animal = check.animal_id
            check.state = 'done'
            if check.result == 'pregnant':
                event.result = 'pregnant'
                animal.write({'reproductive_status': 'pregnant',
                              'expected_calving_date': check.expected_calving_date})
            elif check.result == 'open':
                # a negative check after a confirmed pregnancy documents a pregnancy loss
                event.result = 'lost' if event.result == 'pregnant' else 'open'
                if event == animal._last_breeding_event():
                    animal.write({'reproductive_status': 'open', 'expected_calving_date': False})
            else:
                check._schedule_recheck()
            if check.result in ('pregnant', 'open'):
                event._dairy_clear_alerts(event, event._check_due_summary())
        return True

    def _schedule_recheck(self):
        self.activity_schedule('mail.mail_activity_data_todo', date_deadline=self.date + timedelta(days=14),
                               summary=_('Repeat pregnancy check'),
                               user_id=(self.company_id.dairy_alert_user_id or self.env.user).id)

    def action_cancel(self):
        if any(c.state == 'done' for c in self):
            raise UserError(_('Completed examinations cannot be cancelled.'))
        self.write({'state': 'cancelled'})

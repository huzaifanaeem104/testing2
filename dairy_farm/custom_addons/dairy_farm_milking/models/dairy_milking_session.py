from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

SESSION_STATES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('confirmed', 'Confirmed'),
    ('cancelled', 'Cancelled'),
]

# fields that may still change on a locked session (computed totals,
# chatter, links maintained by other modules)
SESSION_LOCK_EXEMPT = {
    'message_main_attachment_id', 'activity_ids', 'message_follower_ids',
    'batch_ids', 'state', 'cancel_reason', 'confirmed_by_id', 'confirmed_on',
}


def _float_to_time(value):
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return time(min(hours, 23), minutes if hours < 24 else 59)


class DairyMilkingSession(models.Model):
    _name = 'dairy.milking.session'
    _description = 'Milking Session'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.alert.mixin']
    _order = 'date desc, shift_sequence desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True, index=True)
    shift_id = fields.Many2one('dairy.shift', required=True, tracking=True, ondelete='restrict',
                               domain="[('is_milking', '=', True)]", check_company=True)
    shift = fields.Selection(related='shift_id.code', store=True, string='Shift Code')
    shift_sequence = fields.Integer(related='shift_id.sequence', store=True)
    start_datetime = fields.Datetime(compute='_compute_planned_times', store=True, readonly=False)
    end_datetime = fields.Datetime(compute='_compute_planned_times', store=True, readonly=False)
    operator_id = fields.Many2one('res.users', string='Operator', default=lambda self: self.env.user,
                                  required=True, tracking=True)
    location_id = fields.Many2one('dairy.location', string='Milking Location', check_company=True,
                                  help='When set, only animals in this location (or below) are loaded.')
    state = fields.Selection(SESSION_STATES, default='draft', required=True, tracking=True, index=True)
    line_ids = fields.One2many('dairy.milking.line', 'session_id', string='Cow Records', copy=False)
    correction_ids = fields.One2many('dairy.milking.correction', 'session_id', string='Corrections')
    correction_count = fields.Integer(compute='_compute_correction_count')

    total_liters = fields.Float(compute='_compute_totals', store=True, digits=(16, 2))
    saleable_liters = fields.Float(compute='_compute_totals', store=True, digits=(16, 2))
    withheld_liters = fields.Float(compute='_compute_totals', store=True, digits=(16, 2),
                                   help='Milk of animals under a withdrawal restriction.')
    discarded_liters = fields.Float(compute='_compute_totals', store=True, digits=(16, 2),
                                    help='Milk discarded for quality reasons (colostrum, blood, ...).')
    expected_count = fields.Integer(compute='_compute_totals', store=True, string='Animals')
    recorded_count = fields.Integer(compute='_compute_totals', store=True, string='Milked')
    zero_count = fields.Integer(compute='_compute_totals', store=True, string='Zero Yield')
    missed_count = fields.Integer(compute='_compute_totals', store=True, string='Missed')
    pending_count = fields.Integer(compute='_compute_totals', store=True, string='Not Entered')
    average_liters = fields.Float(compute='_compute_totals', store=True, digits=(16, 2),
                                  string='Avg per Milked Cow')

    confirmed_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    confirmed_on = fields.Datetime(readonly=True, copy=False)
    cancel_reason = fields.Text(copy=False)
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    def init(self):
        # one active session per company/date/shift; cancelled sessions may be recreated
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dairy_milking_session_unique_shift
            ON dairy_milking_session (company_id, date, shift_id)
            WHERE state != 'cancelled'
        """)

    # ------------------------------------------------------------------
    @api.depends('date', 'shift_id.start_time', 'shift_id.end_time')
    def _compute_planned_times(self):
        for session in self:
            if not (session.date and session.shift_id):
                session.start_datetime = session.end_datetime = False
                continue
            tz = pytz.timezone(session._dairy_tz())
            start = tz.localize(datetime.combine(session.date, _float_to_time(session.shift_id.start_time)))
            end = tz.localize(datetime.combine(session.date, _float_to_time(session.shift_id.end_time)))
            session.start_datetime = start.astimezone(pytz.utc).replace(tzinfo=None)
            session.end_datetime = end.astimezone(pytz.utc).replace(tzinfo=None)

    def _dairy_tz(self):
        return self.env.user.tz or self.env.company.dairy_alert_user_id.tz or 'Asia/Karachi'

    @api.depends('line_ids.quantity_liters', 'line_ids.entry_status', 'line_ids.milk_destination')
    def _compute_totals(self):
        for session in self:
            lines = session.line_ids
            session.total_liters = sum(lines.mapped('quantity_liters'))
            session.saleable_liters = sum(lines.filtered(lambda l: l.milk_destination == 'saleable').mapped('quantity_liters'))
            session.withheld_liters = sum(lines.filtered(lambda l: l.milk_destination == 'withheld').mapped('quantity_liters'))
            session.discarded_liters = sum(lines.filtered(lambda l: l.milk_destination == 'discarded').mapped('quantity_liters'))
            session.expected_count = len(lines)
            recorded = lines.filtered(lambda l: l.entry_status == 'recorded')
            session.recorded_count = len(recorded)
            session.zero_count = len(lines.filtered(lambda l: l.entry_status == 'zero'))
            session.missed_count = len(lines.filtered(lambda l: l.entry_status == 'missed'))
            session.pending_count = len(lines.filtered(lambda l: l.entry_status == 'pending'))
            session.average_liters = session.total_liters / len(recorded) if recorded else 0.0

    def _compute_correction_count(self):
        for session in self:
            session.correction_count = len(session.correction_ids)

    @api.depends('date', 'shift_id', 'name')
    def _compute_display_name(self):
        for session in self:
            if session.date and session.shift_id:
                session.display_name = f'{session.name} ({session.date} {session.shift_id.name})'
            else:
                session.display_name = session.name

    # ------------------------------------------------------------------
    @api.constrains('date')
    def _check_date(self):
        today = fields.Date.context_today(self)
        for session in self:
            if session.date > today:
                raise ValidationError(_('A milking session cannot be recorded for a future date.'))

    @api.constrains('date', 'shift_id', 'company_id', 'state')
    def _check_duplicate(self):
        for session in self.filtered(lambda s: s.state != 'cancelled'):
            duplicate = self.search_count([
                ('id', '!=', session.id), ('company_id', '=', session.company_id.id),
                ('date', '=', session.date), ('shift_id', '=', session.shift_id.id),
                ('state', '!=', 'cancelled')], limit=1)
            if duplicate:
                raise ValidationError(_('A %(shift)s session already exists for %(date)s.',
                                        shift=session.shift_id.name, date=session.date))

    @api.model_create_multi
    def create(self, vals_list):
        # pending state changes (e.g. a cancellation) must reach the partial unique index first
        self.flush_model(['state', 'date', 'shift_id', 'company_id'])
        for vals in vals_list:
            if vals.get('shift_id') and vals.get('state', 'draft') != 'cancelled':
                date = vals.get('date') or fields.Date.context_today(self)
                company_id = vals.get('company_id') or self.env.company.id
                existing = self.search([('company_id', '=', company_id), ('date', '=', date),
                                        ('shift_id', '=', vals['shift_id']), ('state', '!=', 'cancelled')], limit=1)
                if existing:
                    raise ValidationError(_('A %(shift)s session already exists for %(date)s (%(ref)s).',
                                            shift=existing.shift_id.name, date=existing.date, ref=existing.name))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.milking.session') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('dairy_milking_correction'):
            locked_fields = set(vals) - SESSION_LOCK_EXEMPT
            if locked_fields and any(s.state in ('confirmed', 'cancelled') for s in self):
                raise UserError(_('Confirmed or cancelled milking sessions cannot be modified. '
                                  'Use a correction request instead.'))
        return super().write(vals)

    def unlink(self):
        if any(s.state != 'draft' for s in self):
            raise UserError(_('Only draft milking sessions can be deleted. Cancel the session instead.'))
        return super().unlink()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _eligible_animals(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)] + self.env['dairy.animal']._milking_eligible_domain()
        if self.location_id:
            domain.append(('location_id', 'child_of', self.location_id.id))
        return self.env['dairy.animal'].search(domain)

    def action_load_animals(self):
        """Add a pending line for every eligible cow not yet in the session (idempotent)."""
        for session in self:
            if session.state != 'draft':
                raise UserError(_('Animals can only be loaded into draft sessions.'))
            existing = session.line_ids.animal_id
            missing = session._eligible_animals() - existing
            self.env['dairy.milking.line'].create([{
                'session_id': session.id,
                'animal_id': animal.id,
                'entry_status': 'pending',
            } for animal in missing])
        return True

    def action_submit(self):
        for session in self:
            if session.state != 'draft':
                raise UserError(_('Only draft sessions can be submitted.'))
            if not session.line_ids:
                raise UserError(_('Session %s has no cow records.', session.name))
            if session.pending_count:
                raise UserError(_(
                    '%(count)s cow(s) in %(name)s have no entry yet. Record a quantity, zero yield '
                    'or a missed milking for every animal before submitting.',
                    count=session.pending_count, name=session.name))
            session.state = 'submitted'
            session._dairy_clear_alerts(session, session._incomplete_alert_summary())
        return True

    def _check_supervisor(self):
        if not self.env.user.has_group('dairy_farm_core.group_dairy_manager'):
            raise AccessError(_('Only a Dairy Farm Manager can confirm, return or cancel milking sessions.'))

    def action_confirm(self):
        self._check_supervisor()
        for session in self:
            if session.state != 'submitted':
                raise UserError(_('Only submitted sessions can be confirmed.'))
            session.write({
                'state': 'confirmed',
                'confirmed_by_id': self.env.uid,
                'confirmed_on': fields.Datetime.now(),
            })
        return True

    def action_return_to_draft(self):
        self._check_supervisor()
        for session in self:
            if session.state != 'submitted':
                raise UserError(_('Only submitted sessions can be returned to the operator.'))
            session.state = 'draft'
        return True

    def action_cancel(self):
        self._check_supervisor()
        for session in self:
            if session.state == 'cancelled':
                continue
            if not session.cancel_reason:
                raise UserError(_('Enter a cancellation reason on %s first.', session.name))
            if session.state == 'confirmed':
                session._check_correction_allowed()
            session.state = 'cancelled'
            session.message_post(body=_('Session cancelled: %s', session.cancel_reason))
        return True

    def _check_correction_allowed(self):
        """Hook: dependent modules block corrections when milk was already used downstream."""
        return True

    def action_view_corrections(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_milking.action_dairy_milking_correction')
        action['domain'] = [('session_id', '=', self.id)]
        action['context'] = {'default_session_id': self.id}
        return action

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    def _incomplete_alert_summary(self):
        return _('Milking session not completed')

    @api.model
    def _cron_session_reminders(self):
        """Ensure sessions exist for finished shifts and remind about incomplete ones.

        Idempotent: sessions are unique per date/shift and alerts are only
        scheduled once per session.
        """
        for company in self.env['res.company'].search([]):
            Session = self.with_company(company)
            tz = pytz.timezone(Session._dairy_tz())
            now_local = datetime.now(pytz.utc).astimezone(tz)
            today = now_local.date()
            shifts = self.env['dairy.shift'].search([('company_id', '=', company.id), ('is_milking', '=', True)])
            for day in (today - timedelta(days=1), today):
                for shift in shifts:
                    if day == today and now_local.hour + now_local.minute / 60.0 < shift.end_time:
                        continue
                    session = Session.search([('company_id', '=', company.id), ('date', '=', day),
                                              ('shift_id', '=', shift.id), ('state', '!=', 'cancelled')], limit=1)
                    if not session:
                        session = Session.create({'date': day, 'shift_id': shift.id, 'company_id': company.id,
                                                  'operator_id': (company.dairy_alert_user_id or self.env.ref('base.user_admin')).id})
                        session.action_load_animals()
                    if session.state == 'draft':
                        session._dairy_schedule_alert(
                            session._incomplete_alert_summary(),
                            note=_('%(pending)s animal(s) still have no entry.', pending=session.pending_count),
                            user=session.operator_id)
                    elif session.state == 'submitted':
                        session._dairy_schedule_alert(_('Milking session awaiting confirmation'))

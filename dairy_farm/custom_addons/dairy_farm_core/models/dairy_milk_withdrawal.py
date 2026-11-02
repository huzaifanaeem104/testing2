from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DairyMilkWithdrawal(models.Model):
    """Milk-withdrawal restriction for an animal.

    Milk of a restricted animal is never saleable. A restriction is effective
    from ``start_date`` until it is explicitly released by a veterinarian or
    manager; the release documents the test or veterinary basis and the date
    from which milk is saleable again (never before ``end_date``). Passing the
    planned end date alone does not release the restriction.
    """
    _name = 'dairy.milk.withdrawal'
    _description = 'Milk Withdrawal Restriction'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.alert.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    animal_id = fields.Many2one('dairy.animal', required=True, index=True, ondelete='restrict',
                                tracking=True, check_company=True)
    start_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    end_date = fields.Date(string='Planned End Date', required=True, tracking=True,
                           help='Earliest date the withdrawal period can end according to the '
                                'medicine label / veterinary instruction.')
    reason = fields.Text(required=True)
    origin = fields.Char(string='Source Document')
    source_model = fields.Char(readonly=True)
    source_res_id = fields.Many2oneReference(model_field='source_model', readonly=True)
    state = fields.Selection([
        ('active', 'Active'),
        ('released', 'Released'),
        ('cancelled', 'Cancelled'),
    ], default='active', required=True, tracking=True, index=True)
    release_effective_date = fields.Date(
        string='Milk Saleable From', tracking=True, copy=False,
        help='Milk recorded on or after this date is saleable again.')
    released_by_id = fields.Many2one('res.users', readonly=True, copy=False, tracking=True)
    released_on = fields.Datetime(readonly=True, copy=False)
    release_test_reference = fields.Char(string='Test / Inspection Reference', copy=False, tracking=True)
    release_note = fields.Text(string='Veterinary Release Note', copy=False)
    cancel_reason = fields.Text(copy=False)
    is_overdue_release = fields.Boolean(compute='_compute_is_overdue_release',
                                        search='_search_is_overdue_release',
                                        string='Awaiting Release')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('dates_check', 'CHECK(end_date >= start_date)', 'The end date must be on or after the start date.'),
        ('release_check', "CHECK(state != 'released' OR (release_effective_date IS NOT NULL AND release_effective_date >= end_date))",
         'A released restriction needs a saleable-from date on or after the planned end date.'),
    ]

    # ------------------------------------------------------------------
    # Shared restriction API used by milking and sales
    # ------------------------------------------------------------------
    @api.model
    def _restriction_domain(self, date):
        return [
            ('start_date', '<=', date),
            '|', ('state', '=', 'active'),
            '&', ('state', '=', 'released'), ('release_effective_date', '>', date),
        ]

    @api.model
    def _restricted_animals(self, animals, date):
        """Return the subset of ``animals`` whose milk is restricted on ``date``."""
        if not animals:
            return animals
        restrictions = self.search(
            [('animal_id', 'in', animals.ids)] + self._restriction_domain(date))
        return animals.filtered(lambda a: a.id in restrictions.animal_id.ids)

    # ------------------------------------------------------------------
    def _compute_is_overdue_release(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue_release = rec.state == 'active' and rec.end_date < today

    def _search_is_overdue_release(self, operator, value):
        today = fields.Date.context_today(self)
        domain = [('state', '=', 'active'), ('end_date', '<', today)]
        if (operator == '=') == bool(value):
            return domain
        return [('id', 'not in', self.search(domain).ids)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.milk.withdrawal') or _('New')
        records = super().create(vals_list)
        records._on_restriction_changed()
        return records

    def write(self, vals):
        protected = {'animal_id', 'start_date', 'end_date'}
        if protected & set(vals) and any(rec.state != 'active' for rec in self):
            raise UserError(_('Released or cancelled restrictions cannot be modified.'))
        res = super().write(vals)
        if protected & set(vals) or 'state' in vals or 'release_effective_date' in vals:
            self._on_restriction_changed()
        return res

    def unlink(self):
        if any(rec.state != 'cancelled' for rec in self):
            raise UserError(_('Only cancelled restrictions can be deleted; cancel it with a reason instead.'))
        return super().unlink()

    def _on_restriction_changed(self):
        """Hook for dependent modules (e.g. milking re-flags recorded milk)."""
        return True

    def _check_release_rights(self):
        if not (self.env.user.has_group('dairy_farm_core.group_dairy_veterinarian')
                or self.env.user.has_group('dairy_farm_core.group_dairy_manager')):
            raise AccessError(_('Only veterinarians or dairy managers can release or cancel milk restrictions.'))

    def action_release(self):
        """Open the release form; the release itself is done by ``_do_release``."""
        self.ensure_one()
        self._check_release_rights()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Release Milk Restriction'),
            'res_model': 'dairy.milk.withdrawal.release.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_withdrawal_id': self.id},
        }

    def _do_release(self, effective_date, note, test_reference=False):
        self._check_release_rights()
        for rec in self:
            if rec.state != 'active':
                raise UserError(_('%s is not active.', rec.name))
            if not note:
                raise ValidationError(_('A veterinary release note is required.'))
            if effective_date < rec.end_date:
                raise ValidationError(_(
                    'Milk of %(animal)s cannot be released before the end of the withdrawal '
                    'period (%(date)s).', animal=rec.animal_id.display_name, date=rec.end_date))
            rec.write({
                'state': 'released',
                'release_effective_date': effective_date,
                'release_note': note,
                'release_test_reference': test_reference,
                'released_by_id': self.env.uid,
                'released_on': fields.Datetime.now(),
            })
            rec.message_post(body=_('Restriction released. Milk saleable from %(date)s. Note: %(note)s',
                                    date=effective_date, note=note))
            self._dairy_clear_alerts(rec, rec._release_alert_summary())

    def action_cancel(self):
        self._check_release_rights()
        for rec in self:
            if rec.state != 'active':
                raise UserError(_('Only active restrictions can be cancelled.'))
            if not rec.cancel_reason:
                raise UserError(_('Enter a cancellation reason before cancelling %s.', rec.name))
        self.write({'state': 'cancelled'})

    def _release_alert_summary(self):
        return _('Milk withdrawal awaiting veterinary release')

    @api.model
    def _cron_withdrawal_alerts(self):
        today = fields.Date.context_today(self)
        pending = self.search([('state', '=', 'active'), ('end_date', '<=', today)])
        for rec in pending:
            rec._dairy_schedule_alert(
                rec._release_alert_summary(),
                note=_('Planned withdrawal end date %(date)s has been reached for %(animal)s. '
                       'Milk stays withheld until a veterinarian documents the release.',
                       date=rec.end_date, animal=rec.animal_id.display_name),
                date_deadline=today)
        soon = self.search([('state', '=', 'active'), ('end_date', '=', today + timedelta(days=1))])
        for rec in soon:
            rec._dairy_schedule_alert(_('Milk withdrawal ends tomorrow'), date_deadline=rec.end_date)

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DairyHealthFollowup(models.Model):
    _name = 'dairy.health.followup'
    _description = 'Veterinary Follow-up'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.alert.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    case_id = fields.Many2one('dairy.health.case', required=True, index=True, ondelete='cascade', check_company=True)
    animal_id = fields.Many2one(related='case_id.animal_id', store=True)
    name = fields.Char(string='Purpose', required=True, default=lambda self: _('Follow-up examination'))
    date = fields.Date(string='Scheduled Date', required=True, tracking=True)
    done_date = fields.Date(readonly=True)
    responsible_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    result = fields.Selection([
        ('improving', 'Improving'),
        ('no_change', 'No Change'),
        ('worse', 'Worse'),
        ('recovered', 'Recovered'),
    ])
    findings = fields.Text()
    state = fields.Selection([
        ('planned', 'Planned'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='planned', required=True, tracking=True, index=True)
    company_id = fields.Many2one(related='case_id.company_id', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        followups = super().create(vals_list)
        for followup in followups:
            followup.activity_schedule('mail.mail_activity_data_todo', date_deadline=followup.date,
                                       summary=followup._due_summary(), user_id=followup.responsible_id.id)
        return followups

    def _due_summary(self):
        return _('Veterinary follow-up')

    def action_done(self):
        for followup in self:
            if followup.state != 'planned':
                raise UserError(_('This follow-up is not planned.'))
            if not followup.result:
                raise UserError(_('Record the follow-up result.'))
        self.write({'state': 'done', 'done_date': fields.Date.context_today(self)})
        self._clear_followup_alerts()

    def action_cancel(self):
        if any(f.state == 'done' for f in self):
            raise UserError(_('Completed follow-ups cannot be cancelled.'))
        self.write({'state': 'cancelled'})
        self._clear_followup_alerts()

    def _overdue_summary(self):
        return _('Overdue veterinary follow-up')

    def _clear_followup_alerts(self):
        self._dairy_clear_alerts(self, self._due_summary())
        self._dairy_clear_alerts(self, self._overdue_summary())

    @api.model
    def _cron_overdue_followups(self):
        overdue = self.search([('state', '=', 'planned'), ('date', '<', fields.Date.context_today(self))])
        for followup in overdue:
            followup._dairy_schedule_alert(followup._overdue_summary(), date_deadline=followup.date,
                                           user=followup.responsible_id)

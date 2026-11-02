from odoo import api, fields, models


class DairyAlertMixin(models.AbstractModel):
    """Idempotent activity scheduling shared by all dairy alerts.

    Scheduled jobs call ``_dairy_schedule_alert`` repeatedly; an activity is
    only created when no open activity with the same summary already exists
    on the record, so re-running a cron never duplicates reminders.
    """
    _name = 'dairy.alert.mixin'
    _description = 'Dairy Alert Mixin'

    def _dairy_alert_user(self):
        self.ensure_one()
        company = self.company_id if 'company_id' in self._fields and self.company_id else self.env.company
        user = company.dairy_alert_user_id
        if not user:
            user = self.env.ref('base.user_admin', raise_if_not_found=False)
        return user

    def _dairy_schedule_alert(self, summary, note=None, date_deadline=None, user=None):
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        model_id = self.env['ir.model']._get_id(self._name)
        created = self.env['mail.activity']
        for record in self:
            existing = self.env['mail.activity'].search_count([
                ('res_model_id', '=', model_id),
                ('res_id', '=', record.id),
                ('summary', '=', summary),
            ], limit=1)
            if existing:
                continue
            target_user = user or record._dairy_alert_user()
            created |= record.activity_schedule(
                activity_type_id=activity_type.id,
                summary=summary,
                note=note or '',
                date_deadline=date_deadline or fields.Date.context_today(record),
                user_id=target_user.id if target_user else self.env.uid,
            )
        return created

    @api.model
    def _dairy_clear_alerts(self, records, summary):
        """Mark open alert activities as done once the condition is resolved."""
        if not records:
            return
        activities = self.env['mail.activity'].search([
            ('res_model', '=', records._name),
            ('res_id', 'in', records.ids),
            ('summary', '=', summary),
        ])
        activities.action_feedback(feedback='Resolved automatically.')

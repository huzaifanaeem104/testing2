from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DairyHealthCase(models.Model):
    _name = 'dairy.health.case'
    _description = 'Animal Health Case'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.alert.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    animal_id = fields.Many2one('dairy.animal', required=True, index=True, ondelete='restrict', tracking=True,
                                check_company=True)
    date = fields.Date(string='Reported On', required=True, default=fields.Date.context_today, tracking=True)
    reported_by_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    responsible_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user,
                                     tracking=True)
    veterinarian_id = fields.Many2one('res.partner', string='Veterinarian', tracking=True)
    condition = fields.Selection([
        ('mastitis', 'Mastitis'),
        ('lameness', 'Lameness / Hoof'),
        ('fever', 'Fever / Infection'),
        ('digestive', 'Digestive / Bloat'),
        ('metabolic', 'Metabolic (milk fever, ketosis)'),
        ('respiratory', 'Respiratory'),
        ('reproductive', 'Reproductive'),
        ('parasitic', 'Parasitic'),
        ('injury', 'Injury'),
        ('other', 'Other'),
    ], required=True, default='other', tracking=True)
    severity = fields.Selection([
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical'),
    ], default='medium', required=True, tracking=True)
    symptoms = fields.Text(required=True)
    temperature = fields.Float(string='Temperature (°C)')
    diagnosis = fields.Text(tracking=True)
    diagnosis_date = fields.Date()
    treatment_plan = fields.Text()
    isolated = fields.Boolean(string='Isolated from Herd')
    state = fields.Selection([
        ('reported', 'Reported'),
        ('diagnosed', 'Diagnosed'),
        ('treatment', 'Under Treatment'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='reported', required=True, tracking=True, index=True)
    outcome = fields.Selection([
        ('recovered', 'Recovered'),
        ('chronic', 'Chronic / Managed'),
        ('culled', 'Culled'),
        ('died', 'Died'),
        ('referred', 'Referred'),
    ], tracking=True)
    outcome_notes = fields.Text()
    closed_date = fields.Date(readonly=True)
    treatment_ids = fields.One2many('dairy.treatment', 'case_id', string='Treatments')
    followup_ids = fields.One2many('dairy.health.followup', 'case_id', string='Follow-ups')
    treatment_count = fields.Integer(compute='_compute_counts')
    followup_count = fields.Integer(compute='_compute_counts')
    medicine_cost = fields.Monetary(compute='_compute_counts', currency_field='currency_id',
                                    help='Inventory value of medicines administered for this case.')
    has_active_withdrawal = fields.Boolean(related='animal_id.has_active_withdrawal')
    currency_id = fields.Many2one(related='company_id.currency_id')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    def _compute_counts(self):
        for case in self:
            case.treatment_count = len(case.treatment_ids)
            case.followup_count = len(case.followup_ids)
            case.medicine_cost = sum(case.treatment_ids.filtered(lambda t: t.state == 'administered').mapped('cost_amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.health.case') or _('New')
        cases = super().create(vals_list)
        for case in cases.filtered(lambda c: c.severity in ('high', 'critical')):
            case._dairy_schedule_alert(case._urgent_summary(),
                                       note=_('%s reported with %s severity.', case.animal_id.display_name, case.severity))
        return cases

    def unlink(self):
        if any(c.state not in ('reported', 'cancelled') or c.treatment_ids for c in self):
            raise UserError(_('Health cases with a diagnosis or treatments are clinical history; cancel or close them.'))
        return super().unlink()

    def action_diagnose(self):
        for case in self:
            if not case.diagnosis:
                raise UserError(_('Record the diagnosis of %s first.', case.name))
            if case.state != 'reported':
                raise UserError(_('%s is already diagnosed.', case.name))
        self.write({'state': 'diagnosed', 'diagnosis_date': fields.Date.context_today(self)})

    def action_close(self):
        for case in self:
            if case.state in ('closed', 'cancelled'):
                raise UserError(_('%s is already closed.', case.name))
            if not case.outcome:
                raise UserError(_('Record the outcome of %s before closing it.', case.name))
            if case.treatment_ids.filtered(lambda t: t.state == 'draft'):
                raise UserError(_('Administer or cancel the pending treatments of %s first.', case.name))
            if case.followup_ids.filtered(lambda f: f.state == 'planned'):
                raise UserError(_('Complete or cancel the planned follow-ups of %s first.', case.name))
        self.write({'state': 'closed', 'closed_date': fields.Date.context_today(self)})
        for case in self:
            case.message_post(body=_('Case closed: %s', dict(self._fields['outcome'].selection)[case.outcome]))
        self._dairy_clear_alerts(self, self._urgent_summary())
        # an open milk restriction is NOT released by closing the case: the vet releases it explicitly

    def action_cancel(self):
        for case in self:
            if case.state == 'closed':
                raise UserError(_('%s is closed; reopen it before cancelling.', case.name))
            if case.treatment_ids.filtered(lambda t: t.state == 'administered'):
                raise UserError(_('%s has administered treatments and cannot be cancelled; close it instead.', case.name))
        self.treatment_ids.filtered(lambda t: t.state == 'draft').action_cancel()
        self.followup_ids.filtered(lambda f: f.state == 'planned').action_cancel()
        self.write({'state': 'cancelled'})
        self._dairy_clear_alerts(self, self._urgent_summary())

    def action_reopen(self):
        for case in self:
            if case.state != 'closed':
                raise UserError(_('Only closed cases can be reopened.'))
            administered = case.treatment_ids.filtered(lambda t: t.state == 'administered')
            case.write({'state': 'treatment' if administered else 'diagnosed', 'closed_date': False})

    def _urgent_summary(self):
        return _('Urgent veterinary attention')

    def action_view_treatments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_health.action_dairy_treatment')
        action['domain'] = [('case_id', '=', self.id)]
        action['context'] = {'default_case_id': self.id}
        return action

    def action_add_treatment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Treatment'),
            'res_model': 'dairy.treatment',
            'view_mode': 'form',
            'context': {'default_case_id': self.id},
        }

    def action_view_withdrawals(self):
        self.ensure_one()
        return self.animal_id.action_view_withdrawals()

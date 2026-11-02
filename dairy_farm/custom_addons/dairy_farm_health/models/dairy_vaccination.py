from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DairyVaccination(models.Model):
    _name = 'dairy.vaccination'
    _description = 'Vaccination'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dairy.alert.mixin', 'dairy.medicine.issue.mixin']
    _order = 'planned_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    animal_id = fields.Many2one('dairy.animal', required=True, index=True, ondelete='restrict', tracking=True,
                                check_company=True, domain="[('active_status', '=', 'active')]")
    product_id = fields.Many2one('product.product', string='Vaccine', required=True, check_company=True,
                                 domain="[('is_dairy_vaccine', '=', True)]", tracking=True)
    disease = fields.Char(help='Disease covered, e.g. FMD, HS, LSD, Brucellosis.')
    planned_date = fields.Date(string='Due Date', required=True, default=fields.Date.context_today, tracking=True)
    date_given = fields.Date(tracking=True)
    dose_qty = fields.Float(string='Dose Quantity', digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit', compute='_compute_uom', store=True, readonly=False)
    uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    lot_id = fields.Many2one('stock.lot', string='Lot / Batch', check_company=True,
                             domain="[('product_id', '=', product_id)]")
    tracking = fields.Selection(related='product_id.tracking')
    administered_by_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    veterinarian_id = fields.Many2one('res.partner', string='Veterinarian')
    next_due_date = fields.Date(compute='_compute_next_due_date', store=True)
    next_vaccination_id = fields.Many2one('dairy.vaccination', readonly=True, copy=False)
    move_id = fields.Many2one('stock.move', readonly=True, copy=False)
    cost_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    withdrawal_id = fields.Many2one('dairy.milk.withdrawal', readonly=True, copy=False)
    state = fields.Selection([
        ('planned', 'Planned'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='planned', required=True, tracking=True, index=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('dose_positive', 'CHECK(dose_qty >= 0)', 'The dose cannot be negative.'),
        ('move_uniq', 'unique(move_id)', 'A stock move can only be linked to one vaccination.'),
    ]

    @api.depends('product_id')
    def _compute_uom(self):
        for vac in self:
            if vac.product_id:
                vac.uom_id = vac.product_id.uom_id

    @api.depends('date_given', 'planned_date', 'product_id.dairy_revaccination_days')
    def _compute_next_due_date(self):
        for vac in self:
            interval = vac.product_id.dairy_revaccination_days
            base = vac.date_given or vac.planned_date
            vac.next_due_date = base + timedelta(days=interval) if interval and base else False

    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for vac in self:
            vac.is_overdue = vac.state == 'planned' and vac.planned_date < today

    def _search_is_overdue(self, operator, value):
        domain = [('state', '=', 'planned'), ('planned_date', '<', fields.Date.context_today(self))]
        if (operator == '=') == bool(value):
            return domain
        return [('id', 'not in', self.search(domain).ids)]

    @api.constrains('date_given')
    def _check_date_given(self):
        for vac in self:
            if vac.date_given and vac.date_given > fields.Date.context_today(vac):
                raise ValidationError(_('The vaccination date cannot be in the future.'))

    def _issue_date(self):
        return self.date_given or fields.Date.context_today(self)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.vaccination') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        allowed = {'notes', 'state', 'next_vaccination_id'}
        if set(vals) - allowed and any(v.state == 'done' for v in self):
            raise UserError(_('Completed vaccinations cannot be modified.'))
        return super().write(vals)

    def unlink(self):
        if any(v.state == 'done' for v in self):
            raise UserError(_('Completed vaccinations are part of the health history.'))
        return super().unlink()

    def action_done(self):
        self._lock_rows()
        for vac in self:
            if vac.state != 'planned':
                raise UserError(_('%s is not planned.', vac.name))
            vac._check_animal_treatable(vac.animal_id)
            date_given = vac.date_given or fields.Date.context_today(vac)
            move, cost = vac._issue_medicine(vac.product_id, vac.dose_qty, vac.uom_id, vac.lot_id, vac.name)
            vals = {'state': 'done', 'date_given': date_given, 'move_id': move.id, 'cost_amount': cost}
            days = vac.product_id.dairy_milk_withdrawal_days
            if days:
                vals['withdrawal_id'] = vac._create_withdrawal(
                    vac.animal_id, date_given, date_given + timedelta(days=days),
                    _('Vaccination %s', vac.product_id.display_name)).id
            super(DairyVaccination, vac).write(vals)
            if vac.next_due_date and not vac.next_vaccination_id:
                vac.next_vaccination_id = vac.copy({
                    'planned_date': vac.next_due_date, 'date_given': False, 'state': 'planned', 'lot_id': False})
            self._dairy_clear_alerts(vac, vac._due_summary())
        return True

    def action_cancel(self):
        if any(v.state == 'done' for v in self):
            raise UserError(_('Completed vaccinations cannot be cancelled.'))
        self.write({'state': 'cancelled'})
        self._dairy_clear_alerts(self, self._due_summary())

    def _due_summary(self):
        return _('Vaccination due')

    @api.model
    def _cron_vaccination_reminders(self):
        today = fields.Date.context_today(self)
        for company in self.env['res.company'].search([]):
            window = today + timedelta(days=company.dairy_vaccination_alert_days or 7)
            for vac in self.search([('company_id', '=', company.id), ('state', '=', 'planned'),
                                    ('planned_date', '<=', window)]):
                vac._dairy_schedule_alert(vac._due_summary(), date_deadline=vac.planned_date,
                                          note=_('%(vaccine)s due for %(animal)s.', vaccine=vac.product_id.display_name,
                                                 animal=vac.animal_id.display_name))

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DairyFeedPlan(models.Model):
    _name = 'dairy.feed.plan'
    _description = 'Feeding Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    description = fields.Char(string='Title')
    date_from = fields.Date(string='Effective From', required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(string='Effective To', tracking=True)
    target_type = fields.Selection([('group', 'Animal Group'), ('animal', 'Individual Animal')],
                                   required=True, default='group', tracking=True)
    group_id = fields.Many2one('dairy.animal.group', check_company=True, tracking=True)
    animal_id = fields.Many2one('dairy.animal', check_company=True, tracking=True)
    head_count = fields.Integer(compute='_compute_head_count', help='Active animals currently targeted.')
    responsible_id = fields.Many2one('res.users', default=lambda self: self.env.user, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ], default='draft', required=True, tracking=True)
    line_ids = fields.One2many('dairy.feed.plan.line', 'plan_id', string='Ration Lines', copy=True)
    consumption_ids = fields.One2many('dairy.feed.consumption', 'plan_id', string='Consumption')
    consumption_count = fields.Integer(compute='_compute_consumption_count')
    notes = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('dates_check', 'CHECK(date_to IS NULL OR date_to >= date_from)', 'The end date must follow the start date.'),
    ]

    @api.constrains('target_type', 'group_id', 'animal_id')
    def _check_target(self):
        for plan in self:
            if plan.target_type == 'group' and not plan.group_id:
                raise ValidationError(_('Select the animal group of the feeding plan.'))
            if plan.target_type == 'animal' and not plan.animal_id:
                raise ValidationError(_('Select the animal of the feeding plan.'))

    @api.depends('target_type', 'group_id', 'animal_id')
    def _compute_head_count(self):
        for plan in self:
            plan.head_count = len(plan._target_animals())

    def _compute_consumption_count(self):
        for plan in self:
            plan.consumption_count = len(plan.consumption_ids)

    def _target_animals(self):
        self.ensure_one()
        if self.target_type == 'animal':
            return self.animal_id.filtered(lambda a: a.active_status == 'active')
        return self.group_id.animal_ids.filtered(lambda a: a.active_status == 'active')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.feed.plan') or _('New')
        return super().create(vals_list)

    def action_activate(self):
        for plan in self:
            if not plan.line_ids:
                raise UserError(_('Add at least one ration line to %s.', plan.name))
        self.write({'state': 'active'})

    def action_close(self):
        self.write({'state': 'closed', 'date_to': fields.Date.context_today(self)})

    def action_reset_draft(self):
        if any(plan.consumption_ids.filtered(lambda c: c.state == 'done') for plan in self):
            raise UserError(_('Plans with posted consumption cannot return to draft; close and copy them instead.'))
        self.write({'state': 'draft'})

    def action_generate_consumption(self):
        """Open the wizard creating draft consumption records for a date."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Feeding Records'),
            'res_model': 'dairy.feed.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_plan_ids': [(6, 0, self.ids)]},
        }

    def _generate_consumption(self, date):
        """Create draft consumption lines from active plans (idempotent per line/date/shift)."""
        Consumption = self.env['dairy.feed.consumption']
        created = Consumption
        for plan in self:
            if plan.state != 'active':
                raise UserError(_('%s is not active.', plan.name))
            if date < plan.date_from or (plan.date_to and date > plan.date_to):
                raise UserError(_('%(date)s is outside the validity of %(plan)s.', date=date, plan=plan.name))
            for line in plan.line_ids:
                exists = Consumption.search_count([
                    ('plan_line_id', '=', line.id), ('date', '=', date),
                    ('shift_id', '=', line.shift_id.id or False), ('state', '!=', 'cancelled')], limit=1)
                if exists:
                    continue
                created |= Consumption.create({
                    'date': date,
                    'shift_id': line.shift_id.id,
                    'plan_id': plan.id,
                    'plan_line_id': line.id,
                    'allocation_type': plan.target_type,
                    'group_id': plan.group_id.id if plan.target_type == 'group' else False,
                    'animal_id': plan.animal_id.id if plan.target_type == 'animal' else False,
                    'product_id': line.product_id.id,
                    'uom_id': line.uom_id.id,
                    'planned_qty': line.planned_qty,
                    'actual_qty': line.planned_qty,
                    'company_id': plan.company_id.id,
                })
        return created

    def action_view_consumption(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_feed.action_dairy_feed_consumption')
        action['domain'] = [('plan_id', '=', self.id)]
        action['context'] = {}
        return action


class DairyFeedPlanLine(models.Model):
    _name = 'dairy.feed.plan.line'
    _description = 'Feeding Plan Line'
    _order = 'plan_id, sequence, id'

    plan_id = fields.Many2one('dairy.feed.plan', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', string='Feed', required=True,
                                 domain="[('is_dairy_feed', '=', True)]")
    shift_id = fields.Many2one('dairy.shift', string='Feeding Shift')
    qty_per_head = fields.Float(string='Qty per Head', required=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit', required=True,
                             compute='_compute_uom_id', store=True, readonly=False, precompute=True)
    uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    head_count = fields.Integer(related='plan_id.head_count')
    planned_qty = fields.Float(compute='_compute_planned_qty', digits='Product Unit of Measure',
                               string='Planned Qty per Feeding', help='Quantity per head x current head count.')
    target_type = fields.Selection(related='plan_id.target_type')
    group_id = fields.Many2one(related='plan_id.group_id')
    animal_id = fields.Many2one(related='plan_id.animal_id')
    instructions = fields.Char(string='Feeding Instructions')
    company_id = fields.Many2one(related='plan_id.company_id', store=True)

    _sql_constraints = [
        ('qty_positive', 'CHECK(qty_per_head > 0)', 'The planned quantity per head must be positive.'),
    ]

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            if line.product_id and (not line.uom_id or line.uom_id.category_id != line.product_id.uom_id.category_id):
                line.uom_id = line.product_id.uom_id

    @api.depends('qty_per_head', 'plan_id.target_type', 'plan_id.group_id', 'plan_id.animal_id')
    def _compute_planned_qty(self):
        for line in self:
            line.planned_qty = line.qty_per_head * (line.plan_id.head_count if line.plan_id else 0)

    @api.constrains('uom_id', 'product_id')
    def _check_uom(self):
        for line in self:
            if line.uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_('The unit of %s must be compatible with the product unit.',
                                        line.product_id.display_name))

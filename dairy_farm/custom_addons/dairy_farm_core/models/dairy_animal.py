from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ANIMAL_TYPES = [
    ('cow', 'Cow'),
    ('heifer', 'Heifer'),
    ('bull', 'Bull'),
    ('calf', 'Calf'),
    ('other', 'Other'),
]

ACTIVE_STATUS = [
    ('active', 'Active'),
    ('sold', 'Sold'),
    ('deceased', 'Deceased'),
    ('inactive', 'Inactive'),
]

PRODUCTION_STATUS = [
    ('lactating', 'Lactating'),
    ('dry', 'Dry'),
    ('growing', 'Growing'),
    ('non_lactating', 'Non-lactating'),
    ('na', 'Not Applicable'),
]


class DairyAnimal(models.Model):
    _name = 'dairy.animal'
    _description = 'Dairy Animal'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin', 'dairy.alert.mixin']
    _order = 'tag_number'
    _rec_names_search = ['name', 'tag_number', 'nickname']
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'), index='trigram')
    tag_number = fields.Char(string='Tag / RFID', required=True, copy=False, tracking=True, index=True)
    nickname = fields.Char(string='Name', tracking=True)
    animal_type = fields.Selection(ANIMAL_TYPES, required=True, default='cow', tracking=True)
    breed_id = fields.Many2one('dairy.breed', tracking=True, ondelete='restrict')
    birth_date = fields.Date(tracking=True)
    age_display = fields.Char(string='Age', compute='_compute_age')
    age_months = fields.Integer(compute='_compute_age')
    gender = fields.Selection([('female', 'Female'), ('male', 'Male')], required=True,
                              default='female', tracking=True)
    color = fields.Integer()
    weight_kg = fields.Float(string='Weight (kg)', tracking=True)

    acquisition_type = fields.Selection([
        ('born', 'Born on Farm'),
        ('purchased', 'Purchased'),
        ('other', 'Other'),
    ], required=True, default='purchased', tracking=True)
    purchase_date = fields.Date(tracking=True)
    purchase_price = fields.Monetary(currency_field='currency_id', tracking=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', check_company=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    dam_id = fields.Many2one('dairy.animal', string='Dam (Mother)', index=True, ondelete='restrict',
                             domain="[('gender', '=', 'female'), ('id', '!=', id)]", check_company=True)
    sire_id = fields.Many2one('dairy.animal', string='Sire (Father)', index=True, ondelete='restrict',
                              domain="[('gender', '=', 'male'), ('id', '!=', id)]", check_company=True)
    sire_reference = fields.Char(help='External sire / semen reference when the sire is not on the farm.')
    offspring_ids = fields.One2many('dairy.animal', 'dam_id', string='Offspring (as Dam)',
                                    context={'active_test': False})
    sired_ids = fields.One2many('dairy.animal', 'sire_id', string='Offspring (as Sire)',
                                context={'active_test': False})
    offspring_count = fields.Integer(compute='_compute_offspring_count')

    location_id = fields.Many2one('dairy.location', tracking=True, check_company=True, index=True)
    group_id = fields.Many2one('dairy.animal.group', string='Group', tracking=True,
                               check_company=True, index=True)

    active = fields.Boolean(default=True, tracking=True)
    active_status = fields.Selection(ACTIVE_STATUS, string='Lifecycle Status', required=True,
                                     default='active', tracking=True, index=True)
    production_status = fields.Selection(PRODUCTION_STATUS, required=True, default='non_lactating',
                                         tracking=True, index=True)
    lactation_number = fields.Integer(tracking=True, help='Number of completed calvings.')
    last_calving_date = fields.Date(tracking=True)
    dry_off_date = fields.Date(tracking=True)
    days_in_milk = fields.Integer(compute='_compute_days_in_milk', string='Days in Milk')

    exit_date = fields.Date(tracking=True)
    exit_reason = fields.Text()
    buyer_id = fields.Many2one('res.partner', string='Buyer', check_company=True)
    sale_price = fields.Monetary(currency_field='currency_id')

    notes = fields.Html()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    withdrawal_ids = fields.One2many('dairy.milk.withdrawal', 'animal_id', string='Milk Withdrawals')
    withdrawal_count = fields.Integer(compute='_compute_withdrawal_count')
    has_active_withdrawal = fields.Boolean(compute='_compute_has_active_withdrawal',
                                           search='_search_has_active_withdrawal',
                                           string='Milk Restricted')
    is_milking_eligible = fields.Boolean(compute='_compute_is_milking_eligible',
                                         search='_search_is_milking_eligible')

    _sql_constraints = [
        ('tag_company_uniq', 'unique(tag_number, company_id)',
         'Another animal already uses this tag number.'),
        ('purchase_price_positive', 'CHECK(purchase_price IS NULL OR purchase_price >= 0)',
         'The purchase price cannot be negative.'),
        ('weight_positive', 'CHECK(weight_kg IS NULL OR weight_kg >= 0)', 'Weight cannot be negative.'),
        ('lactation_positive', 'CHECK(lactation_number >= 0)', 'Lactation number cannot be negative.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('birth_date')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for animal in self:
            if animal.birth_date and animal.birth_date <= today:
                delta = relativedelta(today, animal.birth_date)
                animal.age_months = delta.years * 12 + delta.months
                animal.age_display = _('%(y)sy %(m)sm', y=delta.years, m=delta.months)
            else:
                animal.age_months = 0
                animal.age_display = False

    @api.depends('last_calving_date', 'production_status')
    def _compute_days_in_milk(self):
        today = fields.Date.context_today(self)
        for animal in self:
            if animal.production_status == 'lactating' and animal.last_calving_date:
                animal.days_in_milk = (today - animal.last_calving_date).days
            else:
                animal.days_in_milk = 0

    def _compute_offspring_count(self):
        for animal in self:
            animal.offspring_count = len(animal.with_context(active_test=False).offspring_ids
                                         | animal.with_context(active_test=False).sired_ids)

    def _compute_withdrawal_count(self):
        data = self.env['dairy.milk.withdrawal']._read_group(
            [('animal_id', 'in', self.ids)], ['animal_id'], ['__count'])
        counts = {animal.id: count for animal, count in data}
        for animal in self:
            animal.withdrawal_count = counts.get(animal.id, 0)

    def _compute_has_active_withdrawal(self):
        today = fields.Date.context_today(self)
        restricted = self.env['dairy.milk.withdrawal']._restricted_animals(self, today)
        for animal in self:
            animal.has_active_withdrawal = animal in restricted

    def _search_has_active_withdrawal(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_('Unsupported search operator.'))
        today = fields.Date.context_today(self)
        restrictions = self.env['dairy.milk.withdrawal'].search(
            self.env['dairy.milk.withdrawal']._restriction_domain(today))
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', restrictions.animal_id.ids)]

    @api.depends('active', 'active_status', 'gender', 'production_status')
    def _compute_is_milking_eligible(self):
        for animal in self:
            animal.is_milking_eligible = animal._is_milking_eligible()

    def _search_is_milking_eligible(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_('Unsupported search operator.'))
        domain = self._milking_eligible_domain()
        if (operator == '=') != bool(value):
            return [('id', 'not in', self.search(domain).ids)]
        return domain

    @api.model
    def _milking_eligible_domain(self):
        return [('active_status', '=', 'active'), ('gender', '=', 'female'),
                ('production_status', '=', 'lactating')]

    def _is_milking_eligible(self):
        self.ensure_one()
        return (self.active and self.active_status == 'active' and self.gender == 'female'
                and self.production_status == 'lactating')

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('dam_id', 'sire_id', 'gender', 'birth_date')
    def _check_parents(self):
        for animal in self:
            if animal.dam_id:
                if animal.dam_id == animal:
                    raise ValidationError(_('An animal cannot be its own dam.'))
                if animal.dam_id.gender != 'female':
                    raise ValidationError(_('The dam of %s must be female.', animal.display_name))
            if animal.sire_id:
                if animal.sire_id == animal:
                    raise ValidationError(_('An animal cannot be its own sire.'))
                if animal.sire_id.gender != 'male':
                    raise ValidationError(_('The sire of %s must be male.', animal.display_name))
            for parent in (animal.dam_id | animal.sire_id):
                if parent.birth_date and animal.birth_date and parent.birth_date >= animal.birth_date:
                    raise ValidationError(_('A parent must be born before its offspring (%s).',
                                            animal.display_name))
        if self._has_cycle('dam_id') or self._has_cycle('sire_id'):
            raise ValidationError(_('Parentage cannot be circular.'))

    @api.constrains('birth_date', 'purchase_date', 'exit_date')
    def _check_dates(self):
        today = fields.Date.context_today(self)
        for animal in self:
            if animal.birth_date and animal.birth_date > today:
                raise ValidationError(_('Birth date cannot be in the future.'))
            if animal.birth_date and animal.purchase_date and animal.purchase_date < animal.birth_date:
                raise ValidationError(_('Purchase date cannot be before the birth date.'))
            if animal.exit_date and animal.birth_date and animal.exit_date < animal.birth_date:
                raise ValidationError(_('Exit date cannot be before the birth date.'))

    @api.constrains('gender', 'animal_type', 'production_status')
    def _check_type_consistency(self):
        for animal in self:
            if animal.animal_type in ('cow', 'heifer') and animal.gender != 'female':
                raise ValidationError(_('Cows and heifers must be female.'))
            if animal.animal_type == 'bull' and animal.gender != 'male':
                raise ValidationError(_('Bulls must be male.'))
            if animal.production_status in ('lactating', 'dry') and animal.gender != 'female':
                raise ValidationError(_('Only female animals can be lactating or dry.'))

    @api.constrains('active_status', 'exit_date')
    def _check_exit(self):
        for animal in self:
            if animal.active_status in ('sold', 'deceased') and not animal.exit_date:
                raise ValidationError(_('An exit date is required for sold or deceased animals.'))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.onchange('animal_type')
    def _onchange_animal_type(self):
        if self.animal_type == 'bull':
            self.gender = 'male'
            self.production_status = 'na'
        elif self.animal_type in ('cow', 'heifer'):
            self.gender = 'female'
            if self.animal_type == 'heifer':
                self.production_status = 'growing'
        elif self.animal_type == 'calf':
            self.production_status = 'growing'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('dairy.animal') or _('New')
            if 'production_status' not in vals:
                vals['production_status'] = {
                    'calf': 'growing', 'heifer': 'growing', 'bull': 'na', 'other': 'na',
                }.get(vals.get('animal_type', 'cow'), 'non_lactating')
        return super().create(vals_list)

    @api.depends('tag_number', 'nickname')
    def _compute_display_name(self):
        for animal in self:
            label = animal.tag_number or animal.name or ''
            if animal.nickname:
                label = f'{label} - {animal.nickname}'
            animal.display_name = label

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default)
        for animal, vals in zip(self, vals_list):
            if 'tag_number' not in default:
                vals['tag_number'] = _('%s (copy)', animal.tag_number)
        return vals_list

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_exit_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Record Exit'),
            'res_model': 'dairy.animal.exit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_animal_id': self.id},
        }

    def action_reactivate(self):
        for animal in self:
            if animal.active_status == 'deceased':
                raise UserError(_('A deceased animal cannot be reactivated.'))
        self.write({'active': True, 'active_status': 'active', 'exit_date': False})

    def action_dry_off(self):
        today = fields.Date.context_today(self)
        for animal in self:
            if animal.production_status != 'lactating':
                raise UserError(_('%s is not lactating.', animal.display_name))
        self.write({'production_status': 'dry', 'dry_off_date': today})

    def action_start_lactation(self):
        for animal in self:
            if animal.gender != 'female' or animal.active_status != 'active':
                raise UserError(_('Only active female animals can start a lactation.'))
        self.write({'production_status': 'lactating'})

    def action_view_offspring(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_core.action_dairy_animal')
        action['domain'] = ['|', ('dam_id', '=', self.id), ('sire_id', '=', self.id)]
        action['context'] = {'active_test': False}
        return action

    def action_view_withdrawals(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_core.action_dairy_milk_withdrawal')
        action['domain'] = [('animal_id', '=', self.id)]
        action['context'] = {'default_animal_id': self.id}
        return action

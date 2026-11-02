from odoo import api, fields, models


class DairyAnimalGroup(models.Model):
    _name = 'dairy.animal.group'
    _description = 'Animal Group'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    group_type = fields.Selection([
        ('lactating', 'Lactating Cows'),
        ('dry', 'Dry Cows'),
        ('heifer', 'Heifers'),
        ('calf', 'Calves'),
        ('bull', 'Bulls'),
        ('sick', 'Sick / Quarantine'),
        ('other', 'Other'),
    ], default='other', required=True)
    location_id = fields.Many2one('dairy.location', check_company=True)
    responsible_id = fields.Many2one('res.users', string='Responsible')
    animal_ids = fields.One2many('dairy.animal', 'group_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count', string='Head Count')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'The group name must be unique per company.'),
    ]

    @api.depends('animal_ids.active_status')
    def _compute_animal_count(self):
        data = self.env['dairy.animal']._read_group(
            [('group_id', 'in', self.ids), ('active_status', '=', 'active')],
            ['group_id'], ['__count'])
        counts = {group.id: count for group, count in data}
        for group in self:
            group.animal_count = counts.get(group.id, 0)

    def action_view_animals(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_core.action_dairy_animal')
        action['domain'] = [('group_id', '=', self.id)]
        action['context'] = {'default_group_id': self.id}
        return action

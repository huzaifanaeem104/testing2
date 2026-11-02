from odoo import api, fields, models


class DairyBreed(models.Model):
    _name = 'dairy.breed'
    _description = 'Animal Breed'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    origin = fields.Char(string='Origin / Country')
    expected_daily_yield = fields.Float(
        string='Expected Daily Yield (L)',
        help='Reference yield used for performance comparisons.')
    description = fields.Text()
    active = fields.Boolean(default=True)
    animal_ids = fields.One2many('dairy.animal', 'breed_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'A breed with this name already exists.'),
    ]

    @api.depends('animal_ids')
    def _compute_animal_count(self):
        data = self.env['dairy.animal']._read_group(
            [('breed_id', 'in', self.ids)], ['breed_id'], ['__count'])
        counts = {breed.id: count for breed, count in data}
        for breed in self:
            breed.animal_count = counts.get(breed.id, 0)

    def action_view_animals(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_core.action_dairy_animal')
        action['domain'] = [('breed_id', '=', self.id)]
        action['context'] = {'default_breed_id': self.id}
        return action

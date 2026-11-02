from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DairyLocation(models.Model):
    _name = 'dairy.location'
    _description = 'Farm Location'
    _order = 'complete_name'
    _rec_name = 'complete_name'
    _check_company_auto = True

    name = fields.Char(required=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True, recursive=True)
    code = fields.Char()
    location_type = fields.Selection([
        ('farm', 'Farm'),
        ('barn', 'Barn / Shed'),
        ('pen', 'Pen'),
        ('paddock', 'Paddock / Pasture'),
        ('parlour', 'Milking Parlour'),
        ('calf_unit', 'Calf Unit'),
        ('quarantine', 'Quarantine / Sick Bay'),
        ('other', 'Other'),
    ], default='barn', required=True)
    parent_id = fields.Many2one('dairy.location', string='Parent Location',
                                index=True, ondelete='restrict', check_company=True)
    child_ids = fields.One2many('dairy.location', 'parent_id', string='Sub-locations')
    capacity = fields.Integer(help='Maximum number of animals.')
    animal_ids = fields.One2many('dairy.animal', 'location_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ('capacity_positive', 'CHECK(capacity >= 0)', 'Capacity cannot be negative.'),
    ]

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for location in self:
            if location.parent_id:
                location.complete_name = f'{location.parent_id.complete_name} / {location.name}'
            else:
                location.complete_name = location.name

    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError(_('A location cannot be its own parent.'))

    def _compute_animal_count(self):
        data = self.env['dairy.animal']._read_group(
            [('location_id', 'in', self.ids)], ['location_id'], ['__count'])
        counts = {loc.id: count for loc, count in data}
        for location in self:
            location.animal_count = counts.get(location.id, 0)

    def action_view_animals(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_core.action_dairy_animal')
        action['domain'] = [('location_id', 'child_of', self.id)]
        action['context'] = {'default_location_id': self.id}
        return action

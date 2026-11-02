from odoo import fields, models


class DairyAnimal(models.Model):
    _inherit = 'dairy.animal'

    health_case_ids = fields.One2many('dairy.health.case', 'animal_id', string='Health Cases')
    vaccination_ids = fields.One2many('dairy.vaccination', 'animal_id', string='Vaccinations')
    treatment_ids = fields.One2many('dairy.treatment', 'animal_id', string='Treatments')
    health_case_count = fields.Integer(compute='_compute_health_counts')
    open_health_case_count = fields.Integer(compute='_compute_health_counts')
    vaccination_count = fields.Integer(compute='_compute_health_counts')

    def _compute_health_counts(self):
        for animal in self:
            animal.health_case_count = len(animal.health_case_ids)
            animal.open_health_case_count = len(animal.health_case_ids.filtered(
                lambda c: c.state not in ('closed', 'cancelled')))
            animal.vaccination_count = len(animal.vaccination_ids.filtered(lambda v: v.state == 'done'))

    def action_view_health_cases(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_health.action_dairy_health_case')
        action['domain'] = [('animal_id', '=', self.id)]
        action['context'] = {'default_animal_id': self.id}
        return action

    def action_view_vaccinations(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_health.action_dairy_vaccination')
        action['domain'] = [('animal_id', '=', self.id)]
        action['context'] = {'default_animal_id': self.id}
        return action

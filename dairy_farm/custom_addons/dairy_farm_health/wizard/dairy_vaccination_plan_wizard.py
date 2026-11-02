from odoo import _, fields, models
from odoo.exceptions import UserError


class DairyVaccinationPlanWizard(models.TransientModel):
    _name = 'dairy.vaccination.plan.wizard'
    _description = 'Plan Herd Vaccination'

    product_id = fields.Many2one('product.product', string='Vaccine', required=True,
                                 domain="[('is_dairy_vaccine', '=', True)]")
    disease = fields.Char()
    planned_date = fields.Date(required=True, default=fields.Date.context_today)
    dose_qty = fields.Float(string='Dose per Animal', digits='Product Unit of Measure')
    group_ids = fields.Many2many('dairy.animal.group', string='Groups')
    animal_ids = fields.Many2many('dairy.animal', string='Animals', domain="[('active_status', '=', 'active')]")

    def action_plan(self):
        self.ensure_one()
        animals = (self.animal_ids | self.group_ids.animal_ids).filtered(lambda a: a.active_status == 'active')
        if not animals:
            raise UserError(_('Select at least one group or animal.'))
        Vaccination = self.env['dairy.vaccination']
        existing = Vaccination.search([('animal_id', 'in', animals.ids), ('product_id', '=', self.product_id.id),
                                       ('planned_date', '=', self.planned_date), ('state', '!=', 'cancelled')])
        to_plan = animals - existing.animal_id
        records = Vaccination.create([{
            'animal_id': animal.id, 'product_id': self.product_id.id, 'disease': self.disease,
            'planned_date': self.planned_date, 'dose_qty': self.dose_qty,
        } for animal in to_plan])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planned Vaccinations'),
            'res_model': 'dairy.vaccination',
            'view_mode': 'list,form',
            'domain': [('id', 'in', (records | existing).ids)],
        }

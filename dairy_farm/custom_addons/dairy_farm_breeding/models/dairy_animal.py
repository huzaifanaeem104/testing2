from odoo import fields, models


class DairyAnimal(models.Model):
    _inherit = 'dairy.animal'

    reproductive_status = fields.Selection([
        ('open', 'Open'),
        ('inseminated', 'Inseminated - Awaiting Check'),
        ('pregnant', 'Pregnant'),
    ], default='open', tracking=True, index=True,
        help='Set by breeding events and pregnancy examinations only.')
    expected_calving_date = fields.Date(tracking=True, readonly=True)
    last_heat_date = fields.Date(readonly=True)
    last_breeding_date = fields.Date(readonly=True)
    breeding_event_ids = fields.One2many('dairy.breeding.event', 'animal_id', string='Breeding Events')
    pregnancy_check_ids = fields.One2many('dairy.pregnancy.check', 'animal_id', string='Pregnancy Checks')
    calving_ids = fields.One2many('dairy.calving.event', 'dam_id', string='Calvings')
    breeding_count = fields.Integer(compute='_compute_breeding_counts')
    calving_count = fields.Integer(compute='_compute_breeding_counts')

    def _compute_breeding_counts(self):
        for animal in self:
            animal.breeding_count = len(animal.breeding_event_ids.filtered(lambda e: e.state == 'done'))
            animal.calving_count = len(animal.calving_ids.filtered(lambda c: c.state == 'done'))

    def _last_breeding_event(self):
        self.ensure_one()
        return self.env['dairy.breeding.event'].search([
            ('animal_id', '=', self.id), ('event_type', '=', 'breeding'), ('state', '=', 'done')],
            order='breeding_date desc, id desc', limit=1)

    def _recompute_reproductive_status(self):
        for animal in self:
            last = animal._last_breeding_event()
            if not last or last.result in ('open', 'lost', 'calved'):
                animal.write({'reproductive_status': 'open', 'expected_calving_date': False})
            elif last.result == 'pending':
                animal.reproductive_status = 'inseminated'

    def action_view_breeding(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_breeding.action_dairy_breeding_event_all')
        action['domain'] = [('animal_id', '=', self.id)]
        action['context'] = {'default_animal_id': self.id}
        return action

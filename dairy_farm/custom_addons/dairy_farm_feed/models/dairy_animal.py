from datetime import timedelta

from odoo import fields, models


class DairyAnimal(models.Model):
    _inherit = 'dairy.animal'

    feed_consumption_ids = fields.Many2many(
        'dairy.feed.consumption', 'dairy_feed_consumption_animal_rel', 'animal_id', 'consumption_id',
        string='Feed Consumption', readonly=True)
    feed_cost_30d = fields.Monetary(compute='_compute_feed_cost_30d', currency_field='currency_id',
                                    string='Feed Cost 30 Days')

    def _compute_feed_cost_30d(self):
        since = fields.Date.context_today(self) - timedelta(days=30)
        data = self.env['dairy.feed.allocation.report']._read_group(
            [('animal_id', 'in', self.ids), ('date', '>', since)], ['animal_id'], ['cost:sum'])
        costs = dict(data)
        for animal in self:
            animal.feed_cost_30d = costs.get(animal, 0.0)

    def action_view_feed_allocation(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_feed.action_dairy_feed_allocation_report')
        action['domain'] = [('animal_id', '=', self.id)]
        return action

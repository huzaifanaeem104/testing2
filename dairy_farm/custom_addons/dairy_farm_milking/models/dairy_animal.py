from datetime import timedelta

from odoo import _, api, fields, models


class DairyAnimal(models.Model):
    _inherit = 'dairy.animal'

    milking_line_ids = fields.One2many('dairy.milking.line', 'animal_id', string='Milking Records')
    milking_record_count = fields.Integer(compute='_compute_milking_stats')
    milk_last_30d = fields.Float(compute='_compute_milking_stats', string='Milk Last 30 Days (L)', digits=(16, 1))
    milk_lactation_total = fields.Float(compute='_compute_milking_stats', string='Current Lactation (L)', digits=(16, 1))
    yield_avg_7d = fields.Float(string='Avg Daily Yield 7d (L)', readonly=True, digits=(16, 2))
    yield_avg_prev_7d = fields.Float(string='Avg Daily Yield Prev. 7d (L)', readonly=True, digits=(16, 2))
    yield_decline_pct = fields.Float(string='Yield Change (%)', readonly=True, digits=(16, 1))
    yield_decline_alert = fields.Boolean(string='Yield Decline', readonly=True, index=True)

    def _compute_milking_stats(self):
        today = fields.Date.context_today(self)
        Line = self.env['dairy.milking.line']
        valid = [('animal_id', 'in', self.ids), ('session_state', '!=', 'cancelled')]
        counts = dict(Line._read_group(valid, ['animal_id'], ['__count']))
        last30 = dict(Line._read_group(valid + [('date', '>', today - timedelta(days=30))],
                                       ['animal_id'], ['quantity_liters:sum']))
        for animal in self:
            animal.milking_record_count = counts.get(animal, 0)
            animal.milk_last_30d = last30.get(animal, 0.0)
            if animal.last_calving_date:
                animal.milk_lactation_total = sum(Line.search(
                    valid[1:] + [('animal_id', '=', animal.id), ('date', '>=', animal.last_calving_date)]
                ).mapped('quantity_liters'))
            else:
                animal.milk_lactation_total = 0.0

    def action_view_milking_lines(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dairy_farm_milking.action_dairy_milking_line_report')
        action['domain'] = [('animal_id', '=', self.id)]
        action['context'] = {'search_default_filter_not_cancelled': 1}
        return action

    def _yield_alert_summary(self):
        return _('Milk yield decline')

    @api.model
    def _cron_update_yield_trends(self):
        """Recompute rolling 7-day averages and alert on significant declines (idempotent)."""
        today = fields.Date.context_today(self)
        Line = self.env['dairy.milking.line']
        base = [('session_state', 'in', ('submitted', 'confirmed'))]
        current = dict(Line._read_group(base + [('date', '>', today - timedelta(days=7)), ('date', '<=', today)],
                                        ['animal_id'], ['quantity_liters:sum']))
        previous = dict(Line._read_group(base + [('date', '>', today - timedelta(days=14)),
                                                 ('date', '<=', today - timedelta(days=7))],
                                         ['animal_id'], ['quantity_liters:sum']))
        animals = self.search([('production_status', '=', 'lactating')]) | self.browse(
            [a.id for a in set(current) | set(previous)])
        for animal in animals:
            avg_now = current.get(animal, 0.0) / 7.0
            avg_prev = previous.get(animal, 0.0) / 7.0
            change = ((avg_now - avg_prev) / avg_prev * 100.0) if avg_prev else 0.0
            threshold = animal.company_id.dairy_yield_decline_pct or 0.0
            alert = bool(avg_prev and animal.production_status == 'lactating' and -change > threshold)
            animal.write({
                'yield_avg_7d': avg_now,
                'yield_avg_prev_7d': avg_prev,
                'yield_decline_pct': change,
                'yield_decline_alert': alert,
            })
            if alert:
                animal._dairy_schedule_alert(
                    animal._yield_alert_summary(),
                    note=_('Average daily yield fell from %(prev).1f L to %(now).1f L (%(chg).0f%%).',
                           prev=avg_prev, now=avg_now, chg=change))
            else:
                self._dairy_clear_alerts(animal, animal._yield_alert_summary())

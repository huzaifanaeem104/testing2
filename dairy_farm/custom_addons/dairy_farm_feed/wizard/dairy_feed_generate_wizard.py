from odoo import _, fields, models


class DairyFeedGenerateWizard(models.TransientModel):
    _name = 'dairy.feed.generate.wizard'
    _description = 'Generate Feeding Records from Plans'

    plan_ids = fields.Many2many('dairy.feed.plan', string='Feeding Plans', required=True,
                                domain="[('state', '=', 'active')]")
    date = fields.Date(required=True, default=fields.Date.context_today)

    def action_generate(self):
        self.ensure_one()
        records = self.plan_ids._generate_consumption(self.date)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Feeding Records'),
            'res_model': 'dairy.feed.consumption',
            'view_mode': 'list,form',
            'domain': [('plan_id', 'in', self.plan_ids.ids), ('date', '=', self.date)],
            'context': {'created_ids': records.ids},
        }

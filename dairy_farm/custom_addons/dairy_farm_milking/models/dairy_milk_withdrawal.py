from odoo import models


class DairyMilkWithdrawal(models.Model):
    _inherit = 'dairy.milk.withdrawal'

    def _on_restriction_changed(self):
        res = super()._on_restriction_changed()
        for restriction in self:
            lines = self.env['dairy.milking.line'].sudo().search([
                ('animal_id', '=', restriction.animal_id.id),
                ('date', '>=', restriction.start_date),
            ])
            lines._update_milk_destination()
        return res

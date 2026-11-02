from odoo import api, fields, models


class DairyWithdrawalReleaseWizard(models.TransientModel):
    _name = 'dairy.milk.withdrawal.release.wizard'
    _description = 'Release Milk Withdrawal'

    withdrawal_id = fields.Many2one('dairy.milk.withdrawal', required=True)
    animal_id = fields.Many2one(related='withdrawal_id.animal_id')
    end_date = fields.Date(related='withdrawal_id.end_date')
    effective_date = fields.Date(string='Milk Saleable From', required=True)
    test_reference = fields.Char(string='Test / Inspection Reference')
    note = fields.Text(string='Veterinary Release Note', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        withdrawal = self.env['dairy.milk.withdrawal'].browse(res.get('withdrawal_id'))
        if withdrawal and 'effective_date' in fields_list:
            res['effective_date'] = max(withdrawal.end_date, fields.Date.context_today(self))
        return res

    def action_release(self):
        self.ensure_one()
        self.withdrawal_id._do_release(self.effective_date, self.note, self.test_reference)
        return {'type': 'ir.actions.act_window_close'}

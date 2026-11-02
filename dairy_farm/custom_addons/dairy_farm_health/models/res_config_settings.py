from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dairy_medicine_location_id = fields.Many2one(
        related='company_id.dairy_medicine_location_id', readonly=False)
    dairy_medicine_consumption_location_id = fields.Many2one(
        related='company_id.dairy_medicine_consumption_location_id', readonly=False)
    dairy_medicine_expense_account_id = fields.Many2one(
        related='company_id.dairy_medicine_consumption_location_id.valuation_in_account_id', readonly=False,
        string='Veterinary & Medicine Expense Account')

    def set_values(self):
        super().set_values()
        location = self.company_id.dairy_medicine_consumption_location_id
        if location and location.valuation_in_account_id != location.valuation_out_account_id:
            location.valuation_out_account_id = location.valuation_in_account_id

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dairy_feed_location_id = fields.Many2one(
        related='company_id.dairy_feed_location_id', readonly=False)
    dairy_feed_consumption_location_id = fields.Many2one(
        related='company_id.dairy_feed_consumption_location_id', readonly=False)
    dairy_feed_wastage_location_id = fields.Many2one(
        related='company_id.dairy_feed_wastage_location_id', readonly=False)
    dairy_feed_expense_account_id = fields.Many2one(
        related='company_id.dairy_feed_consumption_location_id.valuation_in_account_id', readonly=False,
        string='Feed Consumption Expense Account')
    dairy_feed_wastage_account_id = fields.Many2one(
        related='company_id.dairy_feed_wastage_location_id.valuation_in_account_id', readonly=False,
        string='Feed Wastage Expense Account')
    dairy_anglo_saxon_accounting = fields.Boolean(
        related='company_id.anglo_saxon_accounting', string='Anglo-Saxon Accounting')

    def set_values(self):
        super().set_values()
        # returns out of a consumption location must reverse the same expense account
        for location in (self.company_id.dairy_feed_consumption_location_id
                         | self.company_id.dairy_feed_wastage_location_id):
            if location.valuation_in_account_id != location.valuation_out_account_id:
                location.valuation_out_account_id = location.valuation_in_account_id

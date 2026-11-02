from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dairy_alert_user_id = fields.Many2one(
        related='company_id.dairy_alert_user_id', readonly=False)
    dairy_gestation_days = fields.Integer(
        related='company_id.dairy_gestation_days', readonly=False)
    dairy_pregnancy_check_days = fields.Integer(
        related='company_id.dairy_pregnancy_check_days', readonly=False)
    dairy_calving_alert_days = fields.Integer(
        related='company_id.dairy_calving_alert_days', readonly=False)
    dairy_dry_off_days = fields.Integer(
        related='company_id.dairy_dry_off_days', readonly=False)
    dairy_vaccination_alert_days = fields.Integer(
        related='company_id.dairy_vaccination_alert_days', readonly=False)
    dairy_yield_decline_pct = fields.Float(
        related='company_id.dairy_yield_decline_pct', readonly=False)
    dairy_milk_variance_pct = fields.Float(
        related='company_id.dairy_milk_variance_pct', readonly=False)

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dairy_alert_user_id = fields.Many2one(
        'res.users', string='Dairy Alert Responsible',
        help='User who receives automatic dairy reminders (activities) when '
             'no more specific responsible person is set on the record.')
    dairy_gestation_days = fields.Integer(
        string='Gestation Length (days)', default=283,
        help='Used to estimate the calving date from the breeding date.')
    dairy_pregnancy_check_days = fields.Integer(
        string='Pregnancy Check After (days)', default=35,
        help='Days after insemination when the pregnancy examination is due.')
    dairy_calving_alert_days = fields.Integer(
        string='Calving Alert Window (days)', default=21)
    dairy_dry_off_days = fields.Integer(
        string='Dry-off Before Calving (days)', default=60)
    dairy_vaccination_alert_days = fields.Integer(
        string='Vaccination Alert Window (days)', default=7)
    dairy_yield_decline_pct = fields.Float(
        string='Yield Decline Alert (%)', default=20.0,
        help='Raise an alert when the 7-day average yield of a cow drops by '
             'more than this percentage compared with the previous 7 days.')
    dairy_milk_variance_pct = fields.Float(
        string='Collection Variance Tolerance (%)', default=2.0,
        help='Maximum accepted difference between cow-wise recorded milk and '
             'the measured collected quantity of a batch.')

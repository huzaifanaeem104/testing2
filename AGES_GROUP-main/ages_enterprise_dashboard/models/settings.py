# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_ent_contract_expiry_days = fields.Integer(
        string='Contract expiry horizon (days)',
        config_parameter='ages_enterprise_dashboard.contract_expiry_days',
        default=30,
    )
    ages_ent_overdue_grace_days = fields.Integer(
        string='Overdue grace (days)',
        config_parameter='ages_enterprise_dashboard.overdue_grace_days',
        default=0,
    )
    ages_ent_slow_stock_days = fields.Integer(
        string='Slow-moving stock horizon (days)',
        config_parameter='ages_enterprise_dashboard.slow_stock_days',
        default=90,
    )
    ages_ent_critical_queue_count = fields.Integer(
        string='Critical queue size',
        config_parameter='ages_enterprise_dashboard.critical_queue_count',
        default=10,
        help='An exception queue becomes critical when it reaches this number of records.',
    )
    ages_ent_hr_contract_expiry_days = fields.Integer(
        string='Employee contract expiry horizon (days)',
        config_parameter='ages_enterprise_dashboard.hr_contract_expiry_days',
        default=30,
    )
    ages_ent_target_warn_pct = fields.Integer(
        string='Target warning variance %',
        config_parameter='ages_enterprise_dashboard.target_warn_pct',
        default=10,
    )
    ages_ent_target_critical_pct = fields.Integer(
        string='Target critical variance %',
        config_parameter='ages_enterprise_dashboard.target_critical_pct',
        default=20,
    )
    ages_ent_stale_quotation_days = fields.Integer(
        string='Stale quotation horizon (days)',
        config_parameter='ages_enterprise_dashboard.stale_quotation_days',
        default=14,
    )

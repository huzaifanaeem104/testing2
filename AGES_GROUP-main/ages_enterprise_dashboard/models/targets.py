# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesDashboardKpiTarget(models.Model):
    _name = 'ages.dashboard.kpi.target'
    _description = 'AGES dashboard KPI target'
    _order = 'kpi_key, company_id'

    name = fields.Char(compute='_compute_name', store=True)
    kpi_key = fields.Char(required=True, index=True)
    target_value = fields.Float(required=True)
    company_id = fields.Many2one('res.company', ondelete='cascade')
    notes = fields.Char()

    _sql_constraints = [
        (
            'kpi_company_unique',
            'unique(kpi_key, company_id)',
            'A target already exists for this KPI and company.',
        ),
    ]

    @api.depends('kpi_key')
    def _compute_name(self):
        for record in self:
            record.name = record.kpi_key or 'KPI target'

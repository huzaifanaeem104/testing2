# -*- coding: utf-8 -*-

from odoo import api, fields, models


class QualityPoint(models.Model):
    _inherit = 'quality.point'

    worksheet_template = fields.Html(string='Worksheet Template')


class QualityCheck(models.Model):
    _inherit = 'quality.check'

    worksheet = fields.Html(string='Worksheet')

    @api.model_create_multi
    def create(self, vals_list):
        checks = super().create(vals_list)
        checks._prepare_worksheet()
        return checks

    def _prepare_worksheet(self):
        for check in self.filtered(lambda rec: not rec.worksheet and rec.point_id.worksheet_template):
            check.worksheet = check.point_id.worksheet_template

# -*- coding: utf-8 -*-

from odoo import api, models


class PurchaseRequestLine(models.Model):
    _inherit = 'purchase.request.line'

    def _ages_distribution_from_request(self, request):
        if request and hasattr(request, '_ages_analytic_distribution'):
            return request._ages_analytic_distribution()
        return False

    @api.model_create_multi
    def create(self, vals_list):
        Request = self.env['purchase.request']
        for vals in vals_list:
            if vals.get('analytic_distribution') or not vals.get('request_id'):
                continue
            dist = self._ages_distribution_from_request(Request.browse(vals['request_id']))
            if dist:
                vals['analytic_distribution'] = dist
        return super().create(vals_list)

    @api.onchange('product_id')
    def _onchange_ages_product_analytic(self):
        if self.analytic_distribution:
            return
        dist = self._ages_distribution_from_request(self.request_id)
        if dist:
            self.analytic_distribution = dist

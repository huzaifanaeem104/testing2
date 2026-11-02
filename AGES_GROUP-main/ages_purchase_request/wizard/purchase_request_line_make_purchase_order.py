# -*- coding: utf-8 -*-

from odoo import api, models


class PurchaseRequestLineMakePurchaseOrder(models.TransientModel):
    _inherit = 'purchase.request.line.make.purchase.order'

    def _ages_request_dimensions(self):
        requests = self.item_ids.mapped('request_id')
        project = requests.mapped('ages_project_id')[:1]
        analytic = requests.mapped('ages_analytic_account_id')[:1]
        if not analytic and project.account_id:
            analytic = project.account_id
        return project, analytic

    @api.model
    def _prepare_purchase_order(self, picking_type, group_id, company, origin):
        data = super()._prepare_purchase_order(picking_type, group_id, company, origin)
        project, analytic = self._ages_request_dimensions()
        if project:
            data['ages_project_id'] = project.id
        if analytic:
            data['ages_analytic_account_id'] = analytic.id
        return data

    @api.model
    def _prepare_purchase_order_line(self, po, item):
        vals = super()._prepare_purchase_order_line(po, item)
        if vals.get('analytic_distribution'):
            return vals
        request = item.line_id.request_id
        analytic = request.ages_analytic_account_id or po.ages_analytic_account_id
        if analytic:
            vals['analytic_distribution'] = {str(analytic.id): 100}
        return vals

    def make_purchase_order(self):
        project, analytic = self._ages_request_dimensions()
        if self.purchase_order_id and project and not self.purchase_order_id.ages_project_id:
            self.purchase_order_id.write({
                'ages_project_id': project.id,
                'ages_analytic_account_id': analytic.id if analytic else False,
            })
        return super().make_purchase_order()

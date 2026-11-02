# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        tracking=True,
        index=True,
        check_company=True,
        domain="[('company_id', 'in', [company_id, False])]",
        copy=True,
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        tracking=True,
        index=True,
        check_company=True,
        copy=True,
    )

    def _ages_fill_analytic_vals(self, vals):
        if vals.get('ages_project_id') and not vals.get('ages_analytic_account_id'):
            project = self.env['project.project'].browse(vals['ages_project_id'])
            if project.account_id:
                vals['ages_analytic_account_id'] = project.account_id.id
        return vals

    def _ages_analytic_distribution(self):
        self.ensure_one()
        if not self.ages_analytic_account_id:
            return False
        return {str(self.ages_analytic_account_id.id): 100}

    def _ages_sync_line_analytic(self):
        for order in self:
            dist = order._ages_analytic_distribution()
            lines = order.order_line.filtered(
                lambda line: line.display_type not in ('line_section', 'line_note')
            )
            if lines:
                lines.write({'analytic_distribution': dist})

    @api.onchange('ages_project_id')
    def _onchange_ages_project_id(self):
        if self.ages_project_id:
            self.ages_analytic_account_id = self.ages_project_id.account_id
            if self.ages_project_id.company_id:
                self.company_id = self.ages_project_id.company_id
        else:
            self.ages_analytic_account_id = False
        dist = self._ages_analytic_distribution()
        for line in self.order_line:
            if line.display_type in ('line_section', 'line_note'):
                continue
            line.analytic_distribution = dist

    @api.onchange('ages_analytic_account_id')
    def _onchange_ages_analytic_account_id(self):
        dist = self._ages_analytic_distribution()
        for line in self.order_line:
            if line.display_type in ('line_section', 'line_note'):
                continue
            line.analytic_distribution = dist

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ages_fill_analytic_vals(vals)
        orders = super().create(vals_list)
        orders.filtered('ages_analytic_account_id')._ages_sync_line_analytic()
        return orders

    def write(self, vals):
        if vals.get('ages_project_id') and 'ages_analytic_account_id' not in vals:
            project = self.env['project.project'].browse(vals['ages_project_id'])
            if project.account_id:
                vals = dict(vals, ages_analytic_account_id=project.account_id.id)
        res = super().write(vals)
        if any(key in vals for key in ('ages_project_id', 'ages_analytic_account_id')):
            self._ages_sync_line_analytic()
        return res

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['ages_project_id'] = self.ages_project_id.id
        invoice_vals['ages_analytic_account_id'] = self.ages_analytic_account_id.id
        contract = self.ages_project_id.sudo().ages_contract_id
        if contract:
            invoice_vals['ages_contract_id'] = contract.id
        return invoice_vals


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        Order = self.env['purchase.order']
        for vals in vals_list:
            if vals.get('analytic_distribution') or not vals.get('order_id'):
                continue
            order = Order.browse(vals['order_id'])
            dist = order._ages_analytic_distribution() if hasattr(order, '_ages_analytic_distribution') else False
            if dist:
                vals['analytic_distribution'] = dist
        return super().create(vals_list)

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        dist = self.analytic_distribution
        if not dist and self.order_id.ages_analytic_account_id:
            dist = {str(self.order_id.ages_analytic_account_id.id): 100}
        if dist:
            res['analytic_distribution'] = dist
        return res

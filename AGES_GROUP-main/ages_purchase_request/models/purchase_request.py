# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PurchaseRequest(models.Model):
    _inherit = 'purchase.request'

    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        tracking=True,
        index=True,
        check_company=True,
        domain="[('company_id', 'in', [company_id, False])]",
    )
    ages_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        tracking=True,
        index=True,
        check_company=True,
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
        for request in self:
            dist = request._ages_analytic_distribution()
            lines = request.line_ids.filtered(lambda line: not line.cancelled)
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
        self._ages_apply_analytic_to_lines_ui()

    @api.onchange('ages_analytic_account_id')
    def _onchange_ages_analytic_account_id(self):
        self._ages_apply_analytic_to_lines_ui()

    def _ages_apply_analytic_to_lines_ui(self):
        dist = self._ages_analytic_distribution()
        for line in self.line_ids:
            line.analytic_distribution = dist

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ages_fill_analytic_vals(vals)
        requests = super().create(vals_list)
        requests.filtered('ages_analytic_account_id')._ages_sync_line_analytic()
        return requests

    def write(self, vals):
        if vals.get('ages_project_id') and 'ages_analytic_account_id' not in vals:
            project = self.env['project.project'].browse(vals['ages_project_id'])
            if project.account_id:
                vals = dict(vals, ages_analytic_account_id=project.account_id.id)
        res = super().write(vals)
        if any(key in vals for key in ('ages_project_id', 'ages_analytic_account_id')):
            self._ages_sync_line_analytic()
        return res

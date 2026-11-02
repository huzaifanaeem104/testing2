# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AgesContract(models.Model):
    _inherit = 'ages.contract'

    project_id = fields.Many2one(readonly=False)
    analytic_account_id = fields.Many2one(readonly=False)
    location_id = fields.Many2one(readonly=False)

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        contracts._ages_sync_project_links()
        return contracts

    def write(self, vals):
        res = super().write(vals)
        if any(key in vals for key in ('project_id', 'analytic_account_id', 'location_id')):
            self._ages_sync_project_links()
        return res

    def _ages_sync_project_links(self):
        """Keep project / analytic / location pointing at this contract."""
        for contract in self:
            project = contract.project_id
            if not project:
                continue
            project_vals = {}
            if not project.ages_contract_id:
                project_vals['ages_contract_id'] = contract.id
            if contract.location_id and not project.ages_location_id:
                project_vals['ages_location_id'] = contract.location_id.id
            if contract.sub_company_id and not project.ages_sub_company_id:
                project_vals['ages_sub_company_id'] = contract.sub_company_id.id
            if project_vals:
                project.write(project_vals)

            if contract.analytic_account_id:
                contract.analytic_account_id.write({
                    'ages_contract_id': contract.id,
                    'ages_project_id': project.id,
                    'ages_location_id': (
                        contract.location_id.id
                        or project.ages_location_id.id
                    ),
                })
            if contract.location_id:
                contract.location_id.write({
                    'ages_contract_id': contract.id,
                    'ages_project_id': project.id,
                    'ages_analytic_account_id': (
                        contract.analytic_account_id.id
                        or project.account_id.id
                    ),
                })


    def _create_linked_project_analytic_location(self):
        """Reuse the project's location/analytic when the project already exists."""
        self.ensure_one()
        if self.project_id:
            if not self.analytic_account_id and self.project_id.account_id:
                self.analytic_account_id = self.project_id.account_id.id
            if not self.location_id and self.project_id.ages_location_id:
                self.location_id = self.project_id.ages_location_id.id
        # Bind skip-flag on this recordset, then call the parent method directly.
        # super().with_context(...).method() re-enters this override (RecursionError).
        self_ctx = self.with_context(ages_skip_auto_setup=True)
        res = super(AgesContract, self_ctx)._create_linked_project_analytic_location()
        if self.project_id and self.sub_company_id and not self.project_id.ages_sub_company_id:
            self.project_id.ages_sub_company_id = self.sub_company_id.id
        return res


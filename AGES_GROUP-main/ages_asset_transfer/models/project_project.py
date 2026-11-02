# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    ages_asset_count = fields.Integer(
        string='Assets at Project',
        compute='_compute_ages_asset_transfer_counts',
    )
    ages_asset_transfer_count = fields.Integer(
        string='Asset Transfers',
        compute='_compute_ages_asset_transfer_counts',
    )

    def _compute_ages_asset_transfer_counts(self):
        Asset = self.env['account.asset']
        Transfer = self.env['asset.transfer']
        for project in self:
            location = project.ages_location_id
            project.ages_asset_count = Asset.search_count([
                ('current_location_id', '=', location.id),
            ]) if location else 0
            project.ages_asset_transfer_count = Transfer.search_count([
                ('project_id', '=', project.id),
            ])

    def write(self, vals):
        res = super().write(vals)
        if 'ages_location_id' in vals:
            self._ages_sync_location_project_link()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        projects._ages_sync_location_project_link()
        return projects

    def _ages_sync_location_project_link(self):
        for project in self:
            if project.ages_location_id:
                project.ages_location_id.ages_project_id = project.id

    def action_view_ages_assets(self):
        self.ensure_one()
        location = self.ages_location_id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Assets at this Project',
            'res_model': 'account.asset',
            'view_mode': 'list,form',
            'domain': [('current_location_id', '=', location.id)] if location else [('id', '=', False)],
            'context': {
                'default_current_location_id': location.id if location else False,
            },
        }

    def action_view_ages_asset_transfers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asset Transfer History',
            'res_model': 'asset.transfer',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

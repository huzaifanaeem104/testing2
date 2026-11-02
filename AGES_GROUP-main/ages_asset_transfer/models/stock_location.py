# -*- coding: utf-8 -*-

from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    ages_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        index=True,
        copy=False,
        help='Project linked to this site location.',
    )
    ages_asset_count = fields.Integer(
        string='Assets Count',
        compute='_compute_ages_asset_transfer_counts',
    )
    ages_transfer_count = fields.Integer(
        string='Transfer Count',
        compute='_compute_ages_asset_transfer_counts',
    )

    def _compute_ages_asset_transfer_counts(self):
        Asset = self.env['account.asset']
        History = self.env['asset.transfer.history']
        for location in self:
            location.ages_asset_count = Asset.search_count([
                ('current_location_id', '=', location.id),
            ])
            location.ages_transfer_count = History.search_count([
                '|',
                ('location_from_id', '=', location.id),
                ('location_to_id', '=', location.id),
            ])

    def action_view_ages_assets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Assets in Location',
            'res_model': 'account.asset',
            'view_mode': 'list,form',
            'domain': [('current_location_id', '=', self.id)],
            'context': {'default_current_location_id': self.id},
        }

    def action_view_ages_transfers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asset Transfer History',
            'res_model': 'asset.transfer.history',
            'view_mode': 'list,form',
            'domain': [
                '|',
                ('location_from_id', '=', self.id),
                ('location_to_id', '=', self.id),
            ],
        }

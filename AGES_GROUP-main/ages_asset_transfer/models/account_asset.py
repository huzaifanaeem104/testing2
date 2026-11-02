# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    current_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Current Location',
        tracking=True,
        index=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    current_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Current Project',
        related='current_location_id.ages_project_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Stock Product',
        check_company=True,
        help='Optional product used to create an internal stock move when the asset is transferred.',
    )
    transfer_history_ids = fields.One2many(
        comodel_name='asset.transfer.history',
        inverse_name='asset_id',
        string='Transfer History',
    )
    transfer_history_count = fields.Integer(
        string='Transfer History Count',
        compute='_compute_transfer_history_count',
    )

    @api.depends('transfer_history_ids')
    def _compute_transfer_history_count(self):
        for asset in self:
            asset.transfer_history_count = len(asset.transfer_history_ids)

    def action_view_transfer_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Transfer History',
            'res_model': 'asset.transfer.history',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_transfer_this_asset(self):
        """Open a new Asset Transfer prefilled with this asset."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asset Transfer',
            'res_model': 'asset.transfer',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_location_from_id': self.current_location_id.id,
                'default_company_id': self.company_id.id,
                'default_line_ids': [(0, 0, {
                    'asset_id': self.id,
                    'quantity': 1.0,
                })],
            },
        }

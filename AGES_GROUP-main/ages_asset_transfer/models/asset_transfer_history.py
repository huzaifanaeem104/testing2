# -*- coding: utf-8 -*-

from odoo import fields, models


class AssetTransferHistory(models.Model):
    _name = 'asset.transfer.history'
    _description = 'Asset Transfer History'
    _order = 'date desc, id desc'
    _check_company_auto = True

    transfer_id = fields.Many2one(
        comodel_name='asset.transfer',
        string='Transfer',
        required=True,
        ondelete='cascade',
        index=True,
    )
    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    date = fields.Date(string='Date', required=True, index=True)
    location_from_id = fields.Many2one(
        comodel_name='stock.location',
        string='From Location',
        required=True,
        check_company=True,
    )
    location_to_id = fields.Many2one(
        comodel_name='stock.location',
        string='To Location',
        required=True,
        check_company=True,
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        check_company=True,
    )
    reason = fields.Text(string='Reason / Notes')
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Transferred By',
        required=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    name = fields.Char(
        string='Reference',
        related='transfer_id.name',
        store=True,
    )

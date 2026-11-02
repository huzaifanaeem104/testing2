# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AssetTransferLine(models.Model):
    _name = 'asset.transfer.line'
    _description = 'Asset Transfer Line'
    _check_company_auto = True

    transfer_id = fields.Many2one(
        comodel_name='asset.transfer',
        string='Transfer',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='transfer_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(related='transfer_id.currency_id')
    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='Asset',
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id), ('current_location_id', '=', parent.location_from_id)]",
    )
    current_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Current Location',
        related='asset_id.current_location_id',
        readonly=True,
    )
    book_value = fields.Monetary(
        string='Book Value',
        currency_field='currency_id',
        compute='_compute_asset_info',
        store=True,
        readonly=True,
    )
    profile_id = fields.Many2one(
        comodel_name='account.asset.profile',
        string='Asset Profile',
        related='asset_id.profile_id',
        readonly=True,
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True,
    )

    @api.depends('asset_id', 'asset_id.value_residual')
    def _compute_asset_info(self):
        for line in self:
            line.book_value = line.asset_id.value_residual if line.asset_id else 0.0

    @api.onchange('asset_id')
    def _onchange_asset_id(self):
        if self.asset_id and not self.quantity:
            self.quantity = 1.0
        if (
            self.asset_id
            and self.transfer_id.location_from_id
            and self.asset_id.current_location_id != self.transfer_id.location_from_id
        ):
            return {
                'warning': {
                    'title': _('Location mismatch'),
                    'message': _(
                        'Asset %(asset)s is in %(current)s, not in From location %(from_loc)s.',
                        asset=self.asset_id.display_name,
                        current=self.asset_id.current_location_id.display_name or _('(none)'),
                        from_loc=self.transfer_id.location_from_id.display_name,
                    ),
                }
            }

    @api.constrains('asset_id', 'transfer_id')
    def _check_asset_location_and_duplicates(self):
        for line in self:
            transfer = line.transfer_id
            asset = line.asset_id
            if not transfer or not asset or transfer.state in ('done', 'cancelled'):
                continue
            if asset.current_location_id != transfer.location_from_id:
                raise ValidationError(_(
                    'Asset %(asset)s must be in From location %(from_loc)s (currently %(current)s).',
                    asset=asset.display_name,
                    from_loc=transfer.location_from_id.display_name,
                    current=asset.current_location_id.display_name or _('(none)'),
                ))
            other = self.search([
                ('asset_id', '=', asset.id),
                ('id', '!=', line.id),
                ('transfer_id', '!=', transfer.id),
                ('transfer_id.state', 'in', ('draft', 'confirmed')),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    'Asset %(asset)s is already on open transfer %(name)s.',
                    asset=asset.display_name,
                    name=other.transfer_id.display_name,
                ))

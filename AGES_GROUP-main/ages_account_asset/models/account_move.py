# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('account_id')
    def _onchange_account_id_set_asset_category(self):
        if self.account_id:
            category = self.env['account.asset.category'].search([
                ('account_asset_id', '=', self.account_id.id)
            ], limit=1)
            if category:
                self.asset_category_id = category.id

    def asset_create(self):
        for rec in self:
            if not rec.asset_category_id:
                continue

            price_subtotal = rec.currency_id._convert(
                rec.price_subtotal,
                rec.company_currency_id,
                rec.company_id,
                rec.move_id.invoice_date or fields.Date.context_today(rec)
            )

            qty = int(round(rec.quantity)) if rec.quantity and rec.quantity > 1 else 1
            comp_curr = rec.company_currency_id or rec.company_id.currency_id
            unit_val = comp_curr.round(price_subtotal / qty) if comp_curr else round(price_subtotal / qty, 2)
            base_name = rec.name or (rec.product_id.name if rec.product_id else _('Asset'))

            for i in range(1, qty + 1):
                asset_val = unit_val if i < qty else price_subtotal - (unit_val * (qty - 1))
                asset_name = f"{base_name} {i}" if qty > 1 else base_name

                vals = {
                    'name': asset_name,
                    'code': asset_name or False,
                    'category_id': rec.asset_category_id.id,
                    'value': asset_val,
                    'partner_id': rec.move_id.partner_id.id,
                    'company_id': rec.move_id.company_id.id,
                    'currency_id': comp_curr.id if comp_curr else False,
                    'date': rec.move_id.invoice_date or rec.move_id.date,
                    'invoice_id': rec.move_id.id,
                }
                changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
                if changed_vals and 'value' in changed_vals:
                    vals.update(changed_vals['value'])
                asset = self.env['account.asset.asset'].create(vals)
                if rec.asset_category_id.open_asset:
                    if asset.date_first_depreciation == 'manual':
                        asset.first_depreciation_manual_date = asset.date
                    asset.validate()
        return True

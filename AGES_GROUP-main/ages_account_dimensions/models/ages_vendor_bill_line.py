# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ages_vendor_bill_const import AGES_RENT_TYPES


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    ages_is_vendor_retention_line = fields.Boolean(
        string='Vendor Retention Line',
        copy=True,
        default=False,
        help='Technical: line posts AGES-held vendor retention on Retention Money Payables.',
    )
    ages_rent_type = fields.Selection(
        selection=AGES_RENT_TYPES,
        string='Rent Type',
        copy=True,
    )
    ages_rent_hours = fields.Float(
        string='Hours',
        digits='Product Unit of Measure',
        compute='_compute_ages_rent_duration',
        inverse='_inverse_ages_rent_hours',
        store=False,
        readonly=False,
        help='Hours to bill. Amount = Hours × Price.',
    )
    ages_rent_days = fields.Float(
        string='Days',
        digits='Product Unit of Measure',
        compute='_compute_ages_rent_duration',
        inverse='_inverse_ages_rent_days',
        store=False,
        readonly=False,
        help='Days to bill. Amount = Days × Price.',
    )

    @api.depends('quantity', 'ages_rent_type')
    def _compute_ages_rent_duration(self):
        for line in self:
            qty = line.quantity or 0.0
            line.ages_rent_hours = qty if line.ages_rent_type == 'hour' else 0.0
            line.ages_rent_days = qty if line.ages_rent_type == 'day' else 0.0

    def _inverse_ages_rent_hours(self):
        for line in self:
            if line.ages_rent_type == 'hour':
                line.quantity = line.ages_rent_hours or 0.0

    def _inverse_ages_rent_days(self):
        for line in self:
            if line.ages_rent_type == 'day':
                line.quantity = line.ages_rent_days or 0.0

    def _ages_rent_uom(self):
        self.ensure_one()
        xmlid = {
            'hour': 'uom.product_uom_hour',
            'day': 'uom.product_uom_day',
        }.get(self.ages_rent_type)
        if not xmlid:
            return self.env['uom.uom']
        return self.env.ref(xmlid, raise_if_not_found=False) or self.env['uom.uom']

    def _ages_apply_rent_uom(self):
        for line in self:
            if line.display_type in ('line_section', 'line_note') or not line.ages_rent_type:
                continue
            uom = line._ages_rent_uom()
            if not uom:
                continue
            if line.product_id and line.product_uom_category_id and uom.category_id != line.product_uom_category_id:
                continue
            if line.product_uom_id != uom:
                line.product_uom_id = uom

    def _compute_display_type(self):
        super()._compute_display_type()
        for line in self.filtered('ages_is_vendor_retention_line'):
            line.display_type = 'product'

    def action_register_payment(self, ctx=None):
        payable_lines = self.filtered(lambda line: not line.ages_is_vendor_retention_line)
        return super(AccountMoveLine, payable_lines or self).action_register_payment(ctx=ctx)

    def _compute_account_id(self):
        retention_lines = self.filtered('ages_is_vendor_retention_line')
        super(AccountMoveLine, self - retention_lines)._compute_account_id()
        for line in retention_lines:
            account = line.move_id.company_id.ages_vendor_retention_account_id
            if account:
                line.account_id = account

    @api.constrains('account_id', 'display_type')
    def _check_payable_receivable(self):
        super(AccountMoveLine, self.filtered(lambda line: not line.ages_is_vendor_retention_line))._check_payable_receivable()

    @api.onchange('ages_rent_type', 'product_id')
    def _onchange_ages_rent_type(self):
        self._ages_apply_rent_uom()
        if self.ages_rent_type == 'hour':
            self.ages_rent_hours = self.quantity or 0.0
            self.ages_rent_days = 0.0
        elif self.ages_rent_type == 'day':
            self.ages_rent_days = self.quantity or 0.0
            self.ages_rent_hours = 0.0

    @api.onchange('ages_rent_hours')
    def _onchange_ages_rent_hours(self):
        if self.ages_rent_type == 'hour':
            self.quantity = self.ages_rent_hours or 0.0

    @api.onchange('ages_rent_days')
    def _onchange_ages_rent_days(self):
        if self.ages_rent_type == 'day':
            self.quantity = self.ages_rent_days or 0.0

    @api.onchange('product_id')
    def _onchange_ages_bill_type_product(self):
        move = self.move_id
        if not move.is_purchase_document(include_receipts=True):
            return
        bill_type = move.ages_bill_type
        if bill_type in ('subcontract', 'rental') and self.product_id and self.product_id.type != 'service':
            self.product_id = False
            return {
                'warning': {
                    'title': _('Service product required'),
                    'message': _(
                        'Subcontractor and rental bills only allow products of type Service.'
                    ),
                }
            }
        if bill_type == 'rental' and not self.ages_rent_type:
            self.ages_rent_type = 'day'
        if bill_type == 'rental':
            self._ages_apply_rent_uom()

    def _ages_duration_to_quantity_vals(self, vals):
        """Map Hours/Days onto quantity and drop the non-stored UI keys."""
        vals = dict(vals)
        hours = vals.pop('ages_rent_hours', None)
        days = vals.pop('ages_rent_days', None)
        rent_type = vals.get('ages_rent_type')
        if rent_type == 'hour' and hours is not None:
            vals['quantity'] = hours or 0.0
        elif rent_type == 'day' and days is not None:
            vals['quantity'] = days or 0.0
        return vals, hours, days

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            mapped, hours, days = self._ages_duration_to_quantity_vals(vals)
            if 'quantity' not in mapped:
                if hours is not None:
                    mapped['quantity'] = hours or 0.0
                elif days is not None:
                    mapped['quantity'] = days or 0.0
            prepared.append(mapped)
        lines = super().create(prepared)
        lines._ages_apply_rent_uom()
        if not self.env.context.get('ages_syncing_vendor_retention'):
            lines.filtered(
                lambda line: not line.ages_is_vendor_retention_line
            ).move_id._ages_sync_vendor_retention_line()
        return lines

    def write(self, vals):
        orig_keys = set(vals)
        mapped, hours, days = self._ages_duration_to_quantity_vals(vals)
        if 'quantity' not in mapped and (hours is not None or days is not None):
            res = True
            for line in self:
                line_vals = dict(mapped)
                rent_type = line_vals.get('ages_rent_type') or line.ages_rent_type
                if rent_type == 'hour' and hours is not None:
                    line_vals['quantity'] = hours or 0.0
                elif rent_type == 'day' and days is not None:
                    line_vals['quantity'] = days or 0.0
                super(AccountMoveLine, line).write(line_vals)
        else:
            res = super().write(mapped)
        if {'ages_rent_type', 'product_id'} & orig_keys:
            self._ages_apply_rent_uom()
        if self.env.context.get('ages_syncing_vendor_retention'):
            return res
        skip = {'ages_is_vendor_retention_line'}
        if skip.issuperset(orig_keys):
            return res
        self.filtered(
            lambda line: not line.ages_is_vendor_retention_line
        ).move_id._ages_sync_vendor_retention_line()
        return res

    def unlink(self):
        moves = self.filtered(
            lambda line: not line.ages_is_vendor_retention_line
        ).move_id
        if self.filtered('ages_is_vendor_retention_line') and not self.env.context.get('ages_syncing_vendor_retention'):
            posted = self.filtered(lambda line: line.parent_state == 'posted' and line.ages_is_vendor_retention_line)
            if posted:
                raise UserError(_('Posted retention lines cannot be deleted.'))
        res = super().unlink()
        if not self.env.context.get('ages_syncing_vendor_retention') and moves.exists():
            moves._ages_sync_vendor_retention_line()
        return res

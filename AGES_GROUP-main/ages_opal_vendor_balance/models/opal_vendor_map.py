# -*- coding: utf-8 -*-

from odoo import api, fields, models


class OpalVendorMap(models.Model):
    _name = 'opal.vendor.map'
    _description = 'OPAL vendor to Odoo partner map'
    _order = 'partner_id, vendor_name'

    vendor_name = fields.Char(required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner',
        ondelete='set null',
        index=True,
    )
    notes = fields.Char()

    _sql_constraints = [
        ('vendor_name_uniq', 'unique(vendor_name)', 'Each OPAL vendor can be mapped once.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_line_partners()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'vendor_name', 'partner_id'} & set(vals):
            self._sync_line_partners()
        return result

    def unlink(self):
        names = [rec.vendor_name for rec in self]
        result = super().unlink()
        lines = self.env['opal.vendor.project'].search([('vendor_name', 'in', names)])
        accounts = self.env['opal.vendor.project.account'].search([('vendor_name', 'in', names)])
        if lines:
            lines.write({'partner_id': False})
        if accounts:
            accounts.write({'partner_id': False})
        return result

    def _sync_line_partners(self):
        Project = self.env['opal.vendor.project']
        Account = self.env['opal.vendor.project.account']
        for rec in self:
            partner_id = rec.partner_id.id if rec.partner_id else False
            domain = [('vendor_name', '=', rec.vendor_name)]
            Project.search(domain).write({'partner_id': partner_id})
            Account.search(domain).write({'partner_id': partner_id})

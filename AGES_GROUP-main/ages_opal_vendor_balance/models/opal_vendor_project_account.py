# -*- coding: utf-8 -*-

from odoo import fields, models


class OpalVendorProjectAccount(models.Model):
    _name = 'opal.vendor.project.account'
    _description = 'OPAL vendor / client balance by project and account name'
    _order = 'vendor_name, project_code, account_name'

    vendor_name = fields.Char(required=True, index=True)
    project_code = fields.Char(required=True, index=True)
    project_name = fields.Char()
    category = fields.Char()
    account_name = fields.Char(index=True)
    debit = fields.Monetary(currency_field='currency_id')
    credit = fields.Monetary(currency_field='currency_id')
    balance = fields.Monetary(currency_field='currency_id')
    party_type = fields.Selection(
        [('vendor', 'Vendor'), ('client', 'Client')],
        default='vendor',
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    partner_id = fields.Many2one('res.partner', index=True, ondelete='set null')
    project_id = fields.Many2one('project.project', index=True, ondelete='set null')
    import_id = fields.Many2one(
        'opal.vendor.balance.import',
        ondelete='cascade',
        index=True,
    )

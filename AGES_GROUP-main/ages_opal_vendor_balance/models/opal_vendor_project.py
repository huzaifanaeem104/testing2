# -*- coding: utf-8 -*-

from odoo import fields, models


class OpalVendorProject(models.Model):
    _name = 'opal.vendor.project'
    _description = 'OPAL vendor / client balance by project'
    _order = 'party_type, vendor_name, project_code'

    vendor_name = fields.Char(required=True, index=True)
    project_code = fields.Char(required=True, index=True)
    project_name = fields.Char()
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

    _sql_constraints = [
        (
            'vendor_project_type_uniq',
            'unique(vendor_name, project_code, party_type)',
            'Each vendor or client can have one OPAL row per project code.',
        ),
    ]

    def _auto_init(self):
        cr = self._cr
        cr.execute("SELECT to_regclass('public.opal_vendor_project')")
        if cr.fetchone()[0]:
            cr.execute(
                'ALTER TABLE opal_vendor_project '
                'DROP CONSTRAINT IF EXISTS opal_vendor_project_vendor_project_uniq'
            )
        super()._auto_init()

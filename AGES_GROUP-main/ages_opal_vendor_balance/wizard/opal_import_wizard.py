# -*- coding: utf-8 -*-

import base64

from odoo import fields, models, _
from odoo.exceptions import UserError


class OpalImportWizard(models.TransientModel):
    _name = 'opal.import.wizard'
    _description = 'Import OPAL Vendor Balance workbook'

    data_file = fields.Binary(required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only accounting managers can import OPAL reference data.'))
        if not self.data_file:
            raise UserError(_('Please select OPAL Vendor Balance by Project.xlsx (vendors + clients).'))
        record = self.env['opal.vendor.balance.import'].create({
            'data_file': self.data_file,
            'data_filename': self.filename or 'OPAL Vendor Balance by Project.xlsx',
        })
        record._process_import()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('OPAL import complete'),
                'message': record.note or _('Vendors and clients were replaced.'),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'opal_vendor_balance_report',
                    'name': _('OPAL Vendor Balance by Project'),
                    'target': 'main',
                },
            },
        }

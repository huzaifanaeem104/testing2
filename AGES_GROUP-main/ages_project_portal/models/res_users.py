# -*- coding: utf-8 -*-
import hashlib

from odoo import api, fields, models, _


class ResUsers(models.Model):
    _inherit = 'res.users'

    portal_project_id = fields.Many2one(
        'project.project',
        string='Portal Project',
        help='Project used when this user opens the Attendance Portal. '
             'Employees assigned to this project are listed automatically.',
    )
    portal_pin_enabled = fields.Boolean(
        string='Enable Portal PIN',
        default=False,
        help='Require a short PIN after login on the Attendance Portal (shared tablets).',
    )
    portal_pin = fields.Char(
        string='Portal PIN',
        copy=False,
        help='4–6 digit PIN. Stored hashed.',
    )
    portal_pin_hash = fields.Char(
        string='Portal PIN Hash',
        copy=False,
        groups='base.group_system',
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'portal_project_id',
            'portal_pin_enabled',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS

    @api.model
    def _ages_hash_portal_pin(self, pin):
        pin = (pin or '').strip()
        if not pin:
            return False
        return hashlib.sha256(('ages-portal-pin:' + pin).encode('utf-8')).hexdigest()

    def write(self, vals):
        vals = dict(vals)
        if 'portal_pin' in vals:
            pin = vals.pop('portal_pin')
            if pin:
                vals['portal_pin_hash'] = self._ages_hash_portal_pin(pin)
            elif pin is False or pin == '':
                vals['portal_pin_hash'] = False
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('portal_pin'):
                vals['portal_pin_hash'] = self._ages_hash_portal_pin(vals.pop('portal_pin'))
            elif 'portal_pin' in vals:
                vals.pop('portal_pin')
            prepared.append(vals)
        return super().create(prepared)

    def ages_check_portal_pin(self, pin):
        self.ensure_one()
        if not self.portal_pin_enabled or not self.portal_pin_hash:
            return True
        return self.portal_pin_hash == self._ages_hash_portal_pin(pin)

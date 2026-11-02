# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
###############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from odoo.http import request


class UserSelection(models.Model):
    _name = 'user.selection'
    _description = 'User Selection'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        help='Select the user here',
        domain=lambda self: [
            ('id', '!=', self.env.user.id),
            ('active', '=', True),
        ],
    )
    access_ids = fields.One2many(
        'res.groups',
        'user_id',
        help='User groups for the selection',
        string='Group',
        readonly=True,
    )

    def _check_login_as_any_user_access(self):
        if not self.env.user.has_group(
            'login_as_any_user.group_login_as_any_user'
        ):
            raise AccessError(_(
                'You are not allowed to login as another user. '
                'Ask an administrator to grant the Login As Any User right.'
            ))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_login_as_any_user_access()
        return super().create(vals_list)

    @api.onchange('user_id')
    def _onchange_user_id(self):
        self.access_ids = self.user_id.groups_id

    def action_switch(self):
        self.ensure_one()
        self._check_login_as_any_user_access()
        session = request.session
        session.update({
            'previous_user': self.env.user.id,
        })
        session.authenticate_without_password(
            self.env.cr.dbname, self.user_id.login, self.env,
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/',
            'target': 'self',
        }

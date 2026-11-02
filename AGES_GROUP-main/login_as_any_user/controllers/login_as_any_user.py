# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
###############################################################################
from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.translate import _


class UserSwitch(http.Controller):
    """Switch user / switch back to the original admin session."""

    def _can_switch_user(self):
        return request.env.user.has_group(
            'login_as_any_user.group_login_as_any_user'
        )

    @http.route('/switch/user', type='json', auth='user')
    def user_switch(self):
        """Return whether the current user may open the switch wizard."""
        return {
            'can_switch': self._can_switch_user(),
            'is_impersonated': bool(request.session.get('previous_user')),
        }

    @http.route('/switch/admin', type='json', auth='user')
    def switch_admin(self):
        """Switch back to the user who started the impersonation."""
        session = request.session
        previous_id = session.get('previous_user')
        if not previous_id:
            raise AccessError(_(
                'You are not currently logged in as another user.'
            ))
        pre_user = request.env['res.users'].sudo().browse(previous_id)
        if not pre_user.exists() or not pre_user.has_group(
            'login_as_any_user.group_login_as_any_user'
        ):
            raise AccessError(_(
                'You are not allowed to switch back to that user.'
            ))
        session.authenticate_without_password(
            request.env.cr.dbname, pre_user.login, request.env,
        )
        session.pop('previous_user', None)
        return {
            'type': 'ir.actions.act_url',
            'url': '/',
            'target': 'self',
        }

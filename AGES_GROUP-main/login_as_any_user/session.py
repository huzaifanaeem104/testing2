# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
###############################################################################
import odoo
from odoo.exceptions import AccessError
from odoo.http import request, Session
from odoo.modules.registry import Registry
from odoo.tools.translate import _


def authenticate_without_password(self, dbname, login, env):
    """Passwordless login, only for Login As Any User or switch-back."""
    target = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not target:
        raise AccessError(_('Invalid user.'))
    allowed = env.user.has_group('login_as_any_user.group_login_as_any_user')
    switching_back = (
        self.get('previous_user')
        and target.id == self.get('previous_user')
    )
    if not allowed and not switching_back:
        raise AccessError(_('You are not allowed to login as another user.'))

    registry = Registry(dbname)
    pre_uid = target.id
    self.uid = None
    self.pre_login = login
    self.pre_uid = pre_uid
    with registry.cursor() as cr:
        new_env = odoo.api.Environment(cr, pre_uid, {})
        user = new_env['res.users'].browse(pre_uid)
        if not user._mfa_url():
            self.finalize(new_env)
    if request and request.session is self and request.db == dbname:
        request.env = odoo.api.Environment(request.env.cr, self.uid,
                                           self.context)
        request.update_context(**self.context)
    return pre_uid


Session.authenticate_without_password = authenticate_without_password

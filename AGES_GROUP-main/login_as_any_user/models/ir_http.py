# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        user = self.env.user
        if user._is_public():
            return result
        can_switch = user.has_group('login_as_any_user.group_login_as_any_user')
        impersonated = bool(request.session.get('previous_user'))
        result['login_as_any_user'] = can_switch or impersonated
        result['login_as_any_user_can_switch'] = can_switch
        return result

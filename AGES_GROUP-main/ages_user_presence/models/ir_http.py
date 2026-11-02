# -*- coding: utf-8 -*-

import logging

from odoo import api, models, SUPERUSER_ID
from odoo.http import request

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        info['ages_user_presence'] = self.env['ages.user.session']._client_presence_info()
        return info

    def get_frontend_session_info(self):
        info = super().get_frontend_session_info()
        info['ages_user_presence'] = self.env['ages.user.session']._client_presence_info()
        return info

    @classmethod
    def _post_logout(cls):
        super()._post_logout()
        if not request or not getattr(request, 'session', None) or not request.session.sid:
            return
        identifier = request.session.sid[:42]
        try:
            env = request.env
            if env.cr.readonly:
                env.cr.rollback()
                with env.registry.cursor(readonly=False) as cr:
                    write_env = api.Environment(cr, SUPERUSER_ID, {})
                    write_env['ages.user.session']._mark_identifier_logged_out(
                        identifier, reason='logout',
                    )
                    cr.commit()
            else:
                uid = env.uid or SUPERUSER_ID
                env(user=uid)['ages.user.session'].sudo()._mark_identifier_logged_out(
                    identifier, reason='logout',
                )
        except Exception:
            # Logout must still succeed if presence bookkeeping fails.
            _logger.exception('Could not mark presence session logged out')

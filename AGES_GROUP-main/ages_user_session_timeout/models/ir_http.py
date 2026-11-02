# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.http import request, SessionExpiredException

_logger = logging.getLogger(__name__)

_SKIP_PATH_FRAGMENTS = (
    '/web/session/logout',
    '/web/session/destroy',
    '/web/session/authenticate',
    '/web/login',
)

# Activity sync and the warning poll must still run after expiry so they can
# invalidate the session and tell the client. Enforcement happens inside them.
_STATUS_PATH_FRAGMENTS = (
    '/ages_user_session_timeout/check',
    '/ages_user_session_timeout/activity',
)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        try:
            user = request.env.user
            if request.session.uid and user and user._ages_is_timeout_enforced():
                if not user._ages_request_last_activity():
                    user._ages_touch_session(start=True)
                info['ages_session_timeout'] = user._ages_client_timeout_info()
            else:
                info['ages_session_timeout'] = {'enabled': False}
        except Exception:
            info['ages_session_timeout'] = {'enabled': False}
        return info

    @classmethod
    def _auth_method_user(cls):
        super()._auth_method_user()
        cls._ages_enforce_session_timeout()

    @classmethod
    def _ages_enforce_session_timeout(cls):
        if not request or not request.env or not request.session.uid:
            return
        path = (request.httprequest.path or '')
        if any(fragment in path for fragment in _SKIP_PATH_FRAGMENTS):
            return
        if any(fragment in path for fragment in _STATUS_PATH_FRAGMENTS):
            return
        user = request.env.user.sudo()
        if not user or not user._ages_is_timeout_enforced():
            return
        status = user._ages_session_status()
        if status['valid']:
            return
        cls._ages_expire_current_session(status.get('reason') or 'inactivity_timeout')
        raise SessionExpiredException("Session expired because of inactivity")

    @classmethod
    def _ages_expire_current_session(cls, reason='inactivity_timeout'):
        if not request or not request.session:
            return
        user = request.env.user.sudo() if request.env else None
        if user:
            user._ages_log_expiry(reason)
        identifier = request.session.sid[:42] if request.session.sid else False
        if identifier and request.env and 'ages.user.session' in request.env:
            try:
                request.env['ages.user.session'].sudo()._mark_identifier_logged_out(
                    identifier, reason=reason,
                )
            except Exception:
                _logger.exception('Could not mark presence session after inactivity timeout')
        request.session.logout(keep_db=True)

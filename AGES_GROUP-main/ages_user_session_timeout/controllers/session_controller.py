# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class AgesSessionTimeoutController(http.Controller):

    @http.route(
        '/ages_user_session_timeout/check',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def check_session(self):
        user = request.env.user
        if user._ages_is_timeout_enforced() and not user._ages_request_last_activity():
            user._ages_touch_session(start=True)
        status = user._ages_session_status()
        if not status['valid']:
            request.env['ir.http']._ages_expire_current_session(
                status.get('reason') or 'inactivity_timeout',
            )
            return {
                'status': 'success',
                'valid': False,
                'enabled': True,
                'reason': status['reason'],
                'remaining_seconds': 0,
            }
        return {
            'status': 'success',
            **user._ages_client_timeout_info(),
            'valid': True,
            'reason': status['reason'],
        }

    @http.route(
        '/ages_user_session_timeout/activity',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def update_activity(self):
        user = request.env.user
        if not user._ages_is_timeout_enforced():
            return {'status': 'success', 'ignored': True, 'enabled': False, 'valid': True}
        status = user._ages_session_status()
        if not status['valid']:
            request.env['ir.http']._ages_expire_current_session(
                status.get('reason') or 'inactivity_timeout',
            )
            return {
                'status': 'success',
                'valid': False,
                'enabled': True,
                'reason': status['reason'],
            }
        user._ages_touch_session()
        return {
            'status': 'success',
            'valid': True,
            **user._ages_client_timeout_info(),
        }

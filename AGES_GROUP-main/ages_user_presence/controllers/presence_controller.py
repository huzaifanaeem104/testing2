# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class AgesUserPresenceController(http.Controller):

    @http.route(
        '/ages_user_presence/heartbeat',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def heartbeat(self, presence='active', visibility='visible', focused=True, interacted=False):
        return request.env['ages.user.session']._heartbeat_from_request(
            presence=presence,
            visibility=visibility,
            focused=focused,
            interacted=interacted,
        )

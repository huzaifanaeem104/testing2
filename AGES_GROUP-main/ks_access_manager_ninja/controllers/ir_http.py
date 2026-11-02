# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.http import request

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _authenticate(cls, endpoint):
        res = super(IrHttp, cls)._authenticate(endpoint=endpoint)
        activity_pool = request.env['recent.activity'].sudo()
        activity = activity_pool.search([('ks_session_id', '=', request.session.sid)])
        if not activity:
            activity_pool.create({
                'ks_user_id': request.session.uid, 'ks_login_date': datetime.now(), 'ks_duration': 'Logged in',
                'ks_status': 'active',
                'ks_session_id': request.session.sid
            })
        if activity.filtered(lambda act: act.ks_status == 'close'):
            request.session.logout(keep_db=True)
        return res

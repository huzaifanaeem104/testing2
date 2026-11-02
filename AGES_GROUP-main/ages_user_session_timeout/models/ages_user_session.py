# -*- coding: utf-8 -*-

from datetime import timedelta
import logging

from odoo import api, fields, models
from odoo.http import request, root

_logger = logging.getLogger(__name__)


class AgesUserSession(models.Model):
    _inherit = 'ages.user.session'

    timeout_last_activity = fields.Datetime(
        string='Timeout last activity',
        copy=False,
        help='Last qualifying interaction used for inactivity logout. Presence heartbeats do not update this.',
    )
    timeout_enabled = fields.Boolean(
        string='Inactivity timeout enabled',
        compute='_compute_timeout_info',
    )
    timeout_minutes = fields.Integer(
        string='Inactivity timeout',
        compute='_compute_timeout_info',
    )
    timeout_at = fields.Datetime(
        string='Auto logout at',
        compute='_compute_timeout_info',
    )

    logout_reason = fields.Selection(
        selection_add=[
            ('inactivity_timeout', 'Inactivity Timeout'),
            ('max_session', 'Maximum session length'),
        ],
        ondelete={
            'inactivity_timeout': 'set null',
            'max_session': 'set null',
        },
    )

    @api.depends(
        'user_id',
        'user_id.ages_timeout_policy',
        'user_id.ages_timeout_minutes',
        'user_id.ages_timeout_warning_minutes',
        'user_id.ages_force_session_timeout',
        'timeout_last_activity',
        'last_interaction',
        'login_datetime',
        'presence_state',
    )
    def _compute_timeout_info(self):
        for rec in self:
            cfg = rec.user_id._ages_timeout_config() if rec.user_id else {'enabled': False, 'idle_seconds': 0}
            rec.timeout_enabled = bool(cfg.get('enabled')) and rec.presence_state != 'logged_out'
            rec.timeout_minutes = (cfg.get('idle_seconds') or 0) // 60
            last = rec.timeout_last_activity or rec.last_interaction or rec.login_datetime
            if rec.timeout_enabled and last and cfg.get('idle_seconds'):
                rec.timeout_at = last + timedelta(seconds=cfg['idle_seconds'])
            else:
                rec.timeout_at = False

    def _ages_invalidate_http_sessions(self, reason='inactivity_timeout'):
        sessions = self.filtered(lambda rec: rec.is_logged_in)
        if not sessions:
            return
        identifiers = [ident for ident in sessions.mapped('session_identifier') if ident]
        if identifiers:
            try:
                root.session_store.delete_from_identifiers(identifiers)
            except Exception:
                _logger.exception('Could not delete HTTP sessions after inactivity timeout')
        current_identifier = False
        if request and request.session and request.session.sid:
            current_identifier = request.session.sid[:42]
        hit_current = bool(current_identifier and current_identifier in identifiers)
        sessions._mark_logged_out(reason=reason)
        if hit_current:
            request.session.logout(keep_db=True)

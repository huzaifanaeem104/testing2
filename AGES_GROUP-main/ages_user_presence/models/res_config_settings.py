# -*- coding: utf-8 -*-

from odoo import fields, models

from .ages_user_session import (
    PARAM_ENABLED,
    PARAM_HEARTBEAT,
    PARAM_IDLE_MINUTES,
    PARAM_INACTIVE_SECONDS,
    PARAM_TRACK_PORTAL,
    PARAM_RETENTION_DAYS,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_presence_enabled = fields.Boolean(
        string='Track user presence',
        config_parameter=PARAM_ENABLED,
        default=True,
    )
    ages_presence_heartbeat_seconds = fields.Integer(
        string='Heartbeat interval (seconds)',
        config_parameter=PARAM_HEARTBEAT,
        default=30,
        help='How often the browser reports presence. Keep this at 15 seconds or more.',
    )
    ages_presence_idle_minutes = fields.Integer(
        string='Idle after (minutes)',
        config_parameter=PARAM_IDLE_MINUTES,
        default=5,
        help='Visible Odoo tab with no mouse, keyboard, or navigation is Idle after this delay.',
    )
    ages_presence_inactive_seconds = fields.Integer(
        string='Inactive after (seconds)',
        config_parameter=PARAM_INACTIVE_SECONDS,
        default=90,
        help='No browser heartbeat for this long marks the session Inactive. It stays logged in.',
    )
    ages_presence_track_portal = fields.Boolean(
        string='Track portal users',
        config_parameter=PARAM_TRACK_PORTAL,
        default=False,
    )
    ages_presence_retention_days = fields.Integer(
        string='Keep logged-out history (days)',
        config_parameter=PARAM_RETENTION_DAYS,
        default=14,
    )

# -*- coding: utf-8 -*-

from datetime import timedelta
import logging

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import AccessError
from odoo.http import request, root
from odoo.tools.misc import str2bool

_logger = logging.getLogger(__name__)

PARAM_ENABLED = 'ages_user_session_timeout.enabled'
PARAM_IDLE_MINUTES = 'ages_user_session_timeout.idle_minutes'
PARAM_WARNING_SECONDS = 'ages_user_session_timeout.warning_seconds'
PARAM_MAX_HOURS = 'ages_user_session_timeout.max_session_hours'
PARAM_APPLY_INTERNAL = 'ages_user_session_timeout.apply_internal'
PARAM_APPLY_PORTAL = 'ages_user_session_timeout.apply_portal'
PARAM_EXCLUDE_ADMINS = 'ages_user_session_timeout.exclude_admins'
PARAM_GROUP_IDS = 'ages_user_session_timeout.group_ids'
LEGACY_IDLE_SECONDS = 'user_inactivity_timeout'

TIMEOUT_WRITE_FIELDS = {
    'ages_timeout_policy',
    'ages_timeout_minutes',
    'ages_timeout_warning_minutes',
    'ages_force_session_timeout',
}

SESSION_LAST_ACTIVITY = 'ages_last_activity'
SESSION_STARTED = 'ages_session_started'


def _param_bool(icp, key, default=True):
    return str2bool(icp.get_param(key, str(default)), default)


def _param_int(icp, key, default=0):
    try:
        return int(icp.get_param(key, default) or default)
    except (TypeError, ValueError):
        return default


def _parse_dt(value):
    if not value:
        return False
    if isinstance(value, str):
        return fields.Datetime.to_datetime(value)
    return value


class ResUsers(models.Model):
    _inherit = 'res.users'

    ages_last_activity = fields.Datetime(
        string='Last Activity',
        copy=False,
        help='Most recent confirmed interaction on any of this user\'s browser sessions.',
    )
    ages_session_started = fields.Datetime(
        string='Session Started',
        copy=False,
        help='When the current login on this user record last started. Each browser has its own clock.',
    )
    ages_force_session_timeout = fields.Boolean(
        string='Apply Idle Timeout',
        copy=False,
        help='Kept for compatibility. Prefer Timeout Policy = Custom.',
    )
    ages_timeout_policy = fields.Selection(
        [
            ('default', 'Use default settings'),
            ('custom', 'Custom timeout'),
            ('disabled', 'Disabled'),
        ],
        string='Inactivity timeout',
        default='default',
        required=True,
        copy=False,
        help='Default uses Settings (and who it applies to). Custom uses this user\'s timeout. Disabled never auto-logs this user out for inactivity.',
    )
    ages_timeout_minutes = fields.Integer(
        string='Timeout (minutes)',
        default=15,
        copy=False,
        help='Used when Inactivity timeout is Custom. Minimum 1 minute.',
    )
    ages_timeout_warning_minutes = fields.Integer(
        string='Warning before logout (minutes)',
        default=0,
        copy=False,
        help='Used when Inactivity timeout is Custom. 0 = use the Settings warning.',
    )
    ages_timeout_effective_minutes = fields.Integer(
        string='Effective timeout (minutes)',
        compute='_compute_ages_timeout_effective',
    )

    def _compute_ages_timeout_effective(self):
        for user in self:
            cfg = user._ages_timeout_config()
            user.ages_timeout_effective_minutes = (cfg['idle_seconds'] // 60) if cfg['enabled'] else 0

    @api.model
    def _ages_timeout_params(self):
        icp = self.env['ir.config_parameter'].sudo()
        idle_minutes = max(1, _param_int(icp, PARAM_IDLE_MINUTES, 15))
        legacy_seconds = _param_int(icp, LEGACY_IDLE_SECONDS, 0)
        if not icp.get_param(PARAM_IDLE_MINUTES) and legacy_seconds:
            idle_seconds = max(60, legacy_seconds)
        else:
            idle_seconds = idle_minutes * 60
        warning_seconds = max(10, _param_int(icp, PARAM_WARNING_SECONDS, 60))
        warning_seconds = min(warning_seconds, max(10, idle_seconds - 5))
        max_hours = max(0, _param_int(icp, PARAM_MAX_HOURS, 0))
        group_ids = []
        raw_groups = icp.get_param(PARAM_GROUP_IDS, '') or ''
        for token in raw_groups.split(','):
            token = token.strip()
            if token.isdigit():
                group_ids.append(int(token))
        return {
            'enabled': _param_bool(icp, PARAM_ENABLED, True),
            'idle_seconds': idle_seconds,
            'warning_seconds': warning_seconds,
            'max_session_seconds': max_hours * 3600,
            'apply_internal': _param_bool(icp, PARAM_APPLY_INTERNAL, True),
            'apply_portal': _param_bool(icp, PARAM_APPLY_PORTAL, False),
            'exclude_admins': _param_bool(icp, PARAM_EXCLUDE_ADMINS, True),
            'group_ids': group_ids,
        }

    def _ages_matches_default_scope(self, params):
        self.ensure_one()
        if params['exclude_admins'] and self.has_group('base.group_system'):
            return False
        if params['apply_internal'] and self.has_group('base.group_user'):
            return True
        if params['apply_portal'] and self.has_group('base.group_portal'):
            return True
        if params['group_ids'] and (set(self.groups_id.ids) & set(params['group_ids'])):
            return True
        return False

    def _ages_timeout_config(self):
        """Return the resolved inactivity policy for this user.

        Custom on the user wins. Disabled wins over Settings. Otherwise the
        Settings default applies only if the user is in scope.
        """
        self.ensure_one()
        params = self._ages_timeout_params()
        empty = {
            'enabled': False,
            'idle_seconds': params['idle_seconds'],
            'warning_seconds': params['warning_seconds'],
            'max_session_seconds': params['max_session_seconds'],
        }
        if self.id in (False, SUPERUSER_ID):
            return empty
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        if public and self.id == public.id:
            return empty

        sudo_user = self.sudo()
        policy = sudo_user.ages_timeout_policy or 'default'
        if policy == 'default' and sudo_user.ages_force_session_timeout:
            policy = 'custom'
        if policy == 'disabled':
            return empty

        def _warning(idle_seconds, warning_minutes):
            if warning_minutes:
                warning_seconds = max(10, int(warning_minutes) * 60)
            else:
                warning_seconds = params['warning_seconds']
            return min(warning_seconds, max(10, idle_seconds - 5))

        if policy == 'custom':
            minutes = max(1, sudo_user.ages_timeout_minutes or (params['idle_seconds'] // 60))
            idle_seconds = minutes * 60
            return {
                'enabled': True,
                'idle_seconds': idle_seconds,
                'warning_seconds': _warning(idle_seconds, sudo_user.ages_timeout_warning_minutes),
                'max_session_seconds': params['max_session_seconds'],
            }

        if not params['enabled'] or not self._ages_matches_default_scope(params):
            return empty
        return {
            'enabled': True,
            'idle_seconds': params['idle_seconds'],
            'warning_seconds': params['warning_seconds'],
            'max_session_seconds': params['max_session_seconds'],
        }

    def _ages_is_timeout_enforced(self):
        self.ensure_one()
        return bool(self._ages_timeout_config()['enabled'])

    @api.model
    def _ages_session_identifier(self):
        if request and getattr(request, 'session', None) and request.session.sid:
            return request.session.sid[:42]
        return False

    @api.model
    def _ages_request_last_activity(self):
        if not request or not getattr(request, 'session', None):
            return False
        return _parse_dt(request.session.get(SESSION_LAST_ACTIVITY))

    @api.model
    def _ages_request_session_started(self):
        if not request or not getattr(request, 'session', None):
            return False
        return _parse_dt(request.session.get(SESSION_STARTED))

    def _ages_touch_session(self, start=False):
        user = self.env.user
        if not user or not user._ages_is_timeout_enforced():
            return
        now = fields.Datetime.now()
        now_str = fields.Datetime.to_string(now)
        if request and getattr(request, 'session', None):
            request.session[SESSION_LAST_ACTIVITY] = now_str
            if start or not request.session.get(SESSION_STARTED):
                request.session[SESSION_STARTED] = now_str
        if request and getattr(request.env, 'cr', None) and request.env.cr.readonly:
            return
        self.env.cr.execute(
            """
            UPDATE res_users
               SET ages_last_activity = %s,
                   ages_session_started = CASE
                        WHEN %s OR ages_session_started IS NULL THEN %s
                        ELSE ages_session_started
                   END
             WHERE id = %s
            """,
            (now, start, now, user.id),
        )
        user.invalidate_recordset(['ages_last_activity', 'ages_session_started'])
        identifier = self._ages_session_identifier()
        if identifier and 'ages.user.session' in self.env:
            rec = self.env['ages.user.session'].sudo().search([
                ('session_identifier', '=', identifier),
                ('is_logged_in', '=', True),
            ], limit=1)
            if rec:
                rec.write({
                    'timeout_last_activity': now,
                    'last_interaction': now,
                })

    def _ages_status_from_timestamps(self, last_activity, started, now=None):
        self.ensure_one()
        cfg = self._ages_timeout_config()
        status = {
            'enabled': cfg['enabled'],
            'idle_seconds': cfg['idle_seconds'],
            'warning_seconds': cfg['warning_seconds'],
            'max_session_seconds': cfg['max_session_seconds'],
            'valid': True,
            'remaining_seconds': cfg['idle_seconds'],
            'reason': False,
        }
        if not cfg['enabled']:
            return status
        now = now or fields.Datetime.now()
        last_activity = last_activity or now
        started = started or last_activity
        remaining = int((last_activity + timedelta(seconds=cfg['idle_seconds']) - now).total_seconds())
        reason = False
        if remaining <= 0:
            status['valid'] = False
            reason = 'inactivity_timeout'
            remaining = 0
        if cfg['max_session_seconds']:
            max_remaining = int((started + timedelta(seconds=cfg['max_session_seconds']) - now).total_seconds())
            if max_remaining <= 0:
                status['valid'] = False
                reason = 'max_session'
                remaining = 0
            elif status['valid']:
                remaining = min(remaining, max_remaining)
        status['remaining_seconds'] = max(0, remaining)
        status['reason'] = reason
        return status

    def _ages_session_status(self):
        self.ensure_one()
        last_activity = self._ages_request_last_activity() or self.ages_last_activity
        started = self._ages_request_session_started() or self.ages_session_started or last_activity
        return self._ages_status_from_timestamps(last_activity, started)

    def _ages_client_timeout_info(self):
        self.ensure_one()
        status = self._ages_session_status()
        identifier = self._ages_session_identifier() or ''
        return {
            'enabled': status['enabled'],
            'idle_seconds': status['idle_seconds'],
            'warning_seconds': status['warning_seconds'],
            'max_session_seconds': status['max_session_seconds'],
            'remaining_seconds': status['remaining_seconds'],
            'session_identifier': identifier,
            'session_scope': '%s:%s:%s' % (self.id, identifier, self.env.cr.dbname),
        }

    def _update_last_login(self):
        super()._update_last_login()
        uid = self.env.uid
        if not uid:
            return
        user = self.env['res.users'].browse(uid)
        if user._ages_is_timeout_enforced():
            now = fields.Datetime.now()
            self.env.cr.execute(
                """
                UPDATE res_users
                   SET ages_last_activity = %s,
                       ages_session_started = %s
                 WHERE id = %s
                """,
                (now, now, uid),
            )
            user.invalidate_recordset(['ages_last_activity', 'ages_session_started'])

    def _ages_log_expiry(self, reason):
        _logger.info(
            "Session timeout for user %s (%s), reason=%s",
            self.login,
            self.id,
            reason or 'inactivity_timeout',
        )

    @api.model
    def _ages_sync_timeout_vals(self, vals):
        if 'ages_timeout_policy' in vals and 'ages_force_session_timeout' not in vals:
            vals['ages_force_session_timeout'] = vals['ages_timeout_policy'] == 'custom'
        elif vals.get('ages_force_session_timeout') and 'ages_timeout_policy' not in vals:
            vals['ages_timeout_policy'] = 'custom'
        if 'ages_timeout_minutes' in vals and vals['ages_timeout_minutes'] is not None:
            vals['ages_timeout_minutes'] = max(0, int(vals['ages_timeout_minutes'] or 0))
        if 'ages_timeout_warning_minutes' in vals and vals['ages_timeout_warning_minutes'] is not None:
            vals['ages_timeout_warning_minutes'] = max(0, int(vals['ages_timeout_warning_minutes'] or 0))
        return vals

    def _ages_check_timeout_write(self, vals):
        if self.env.su:
            return
        if not (TIMEOUT_WRITE_FIELDS & set(vals)):
            return
        if not self.env.user.has_group('ages_user_session_timeout.group_session_timeout_manager'):
            raise AccessError(_('You cannot change inactivity timeout policy.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ages_sync_timeout_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        timeout_keys = TIMEOUT_WRITE_FIELDS & set(vals)
        if timeout_keys:
            self._ages_check_timeout_write(vals)
        vals = dict(vals)
        self._ages_sync_timeout_vals(vals)
        timeout_keys = TIMEOUT_WRITE_FIELDS & set(vals)
        if (
            timeout_keys
            and not self.env.su
            and self.env.user.has_group('ages_user_session_timeout.group_session_timeout_manager')
            and not self.env.user.has_group('base.group_erp_manager')
        ):
            timeout_vals = {key: vals.pop(key) for key in list(vals) if key in TIMEOUT_WRITE_FIELDS}
            result = True
            if vals:
                result = super().write(vals)
            self.sudo().write(timeout_vals)
            return result
        return super().write(vals)

    @api.model
    def _cron_expire_idle_sessions(self):
        if 'ages.user.session' not in self.env:
            return
        Session = self.env['ages.user.session'].sudo()
        online = Session.search([('is_logged_in', '=', True)])
        if not online:
            return
        now = fields.Datetime.now()
        by_reason = {
            'inactivity_timeout': Session.browse(),
            'max_session': Session.browse(),
        }
        configs = {}
        for rec in online:
            uid = rec.user_id.id
            if uid not in configs:
                configs[uid] = rec.user_id._ages_timeout_config()
            cfg = configs[uid]
            if not cfg['enabled']:
                continue
            last = rec.timeout_last_activity or rec.last_interaction or rec.login_datetime
            if last and (now - last).total_seconds() >= cfg['idle_seconds']:
                by_reason['inactivity_timeout'] |= rec
                continue
            started = rec.login_datetime
            if cfg['max_session_seconds'] and started and (now - started).total_seconds() >= cfg['max_session_seconds']:
                by_reason['max_session'] |= rec
        for reason, recs in by_reason.items():
            if recs:
                recs._ages_invalidate_http_sessions(reason)

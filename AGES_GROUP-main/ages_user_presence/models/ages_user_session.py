# -*- coding: utf-8 -*-

from datetime import timedelta
import logging

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request, root
from odoo.tools import SQL
from odoo.tools.misc import str2bool
from psycopg2 import IntegrityError

_logger = logging.getLogger(__name__)

PARAM_ENABLED = 'ages_user_presence.enabled'
PARAM_HEARTBEAT = 'ages_user_presence.heartbeat_seconds'
PARAM_IDLE_MINUTES = 'ages_user_presence.idle_minutes'
PARAM_INACTIVE_SECONDS = 'ages_user_presence.inactive_seconds'
PARAM_TRACK_PORTAL = 'ages_user_presence.track_portal'
PARAM_RETENTION_DAYS = 'ages_user_presence.retention_days'

PRESENCE_SELECTION = [
    ('active', 'Active / Using Odoo'),
    ('background', 'Background'),
    ('idle', 'Idle'),
    ('inactive', 'Inactive'),
    ('logged_out', 'Logged Out'),
]
CLIENT_PRESENCE = frozenset({'active', 'background', 'idle'})
VISIBILITY_SELECTION = [
    ('visible', 'Visible'),
    ('hidden', 'Hidden'),
    ('unknown', 'Unknown'),
]
FOCUS_SELECTION = [
    ('focused', 'Focused'),
    ('blurred', 'Not focused'),
    ('unknown', 'Unknown'),
]
LOGOUT_REASON_SELECTION = [
    ('logout', 'User logout'),
    ('force_logout', 'Forced logout'),
    ('expired', 'HTTP session expired'),
]
CHANNEL_TYPE = 'ages.user.presence/updated'
FORCE_LOGOUT_TYPE = 'ages.user.presence/force_logout'


def _param_bool(icp, key, default=True):
    return str2bool(icp.get_param(key, str(default)), default)


def _param_int(icp, key, default=0, minimum=None, maximum=None):
    try:
        value = int(icp.get_param(key, default) or default)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _format_duration(seconds):
    seconds = max(0, int(seconds or 0))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return '%dh %02dm' % (hours, minutes)
    if minutes:
        return '%dm %02ds' % (minutes, secs)
    return '%ds' % secs


class AgesUserSession(models.Model):
    _name = 'ages.user.session'
    _description = 'User Presence Session'
    _order = 'is_logged_in desc, last_heartbeat desc, id desc'
    _log_access = False
    _rec_names_search = ['user_id', 'user_login', 'browser', 'operating_system', 'ip_address']

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade',
    )
    user_login = fields.Char(
        related='user_id.login',
        string='Login',
        store=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        ondelete='set null',
    )
    session_identifier = fields.Char(
        string='Session identifier',
        required=True,
        index=True,
        copy=False,
        help='Internal prefix of the HTTP session key. Never the cookie or token.',
    )
    login_datetime = fields.Datetime(string='Login time', required=True, index=True)
    last_interaction = fields.Datetime(string='Last interaction', index=True)
    last_heartbeat = fields.Datetime(string='Last heartbeat', index=True)
    presence_state = fields.Selection(
        PRESENCE_SELECTION,
        string='Presence',
        required=True,
        default='active',
        index=True,
    )
    authentication_state = fields.Selection(
        [('logged_in', 'Logged In'), ('logged_out', 'Logged Out')],
        string='Authentication',
        compute='_compute_authentication_state',
        store=True,
        index=True,
    )
    is_logged_in = fields.Boolean(
        string='Currently logged in',
        compute='_compute_authentication_state',
        store=True,
        index=True,
    )
    visibility_state = fields.Selection(VISIBILITY_SELECTION, string='Page visibility', default='unknown')
    focus_state = fields.Selection(FOCUS_SELECTION, string='Page focus', default='unknown')
    ip_address = fields.Char(string='IP address')
    user_agent = fields.Char(string='User agent')
    browser = fields.Char(string='Browser')
    operating_system = fields.Char(string='Operating system')
    device_type = fields.Selection(
        [('computer', 'Computer'), ('mobile', 'Mobile')],
        string='Device',
        default='computer',
    )
    logout_datetime = fields.Datetime(string='Logout time')
    logout_reason = fields.Selection(LOGOUT_REASON_SELECTION, string='Logout reason')
    session_duration = fields.Char(
        string='Session duration',
        compute='_compute_session_duration',
    )
    session_duration_seconds = fields.Integer(
        string='Session duration (seconds)',
        compute='_compute_session_duration',
    )
    presence_display = fields.Char(
        string='Presence label',
        compute='_compute_presence_display',
    )
    authentication_display = fields.Char(
        string='Authentication label',
        compute='_compute_presence_display',
    )

    def init(self):
        self.env.cr.execute(SQL(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ages_user_session_active_ident
                ON %s (session_identifier)
             WHERE is_logged_in IS TRUE
            """,
            SQL.identifier(self._table),
        ))
        self.env.cr.execute(SQL(
            """
            CREATE INDEX IF NOT EXISTS ages_user_session_online_heartbeat
                ON %s (last_heartbeat)
             WHERE is_logged_in IS TRUE
            """,
            SQL.identifier(self._table),
        ))

    @api.depends('presence_state')
    def _compute_authentication_state(self):
        for rec in self:
            logged_in = rec.presence_state != 'logged_out'
            rec.is_logged_in = logged_in
            rec.authentication_state = 'logged_in' if logged_in else 'logged_out'

    @api.depends('login_datetime', 'logout_datetime', 'last_heartbeat', 'presence_state')
    def _compute_session_duration(self):
        now = fields.Datetime.now()
        for rec in self:
            start = rec.login_datetime
            if not start:
                rec.session_duration_seconds = 0
                rec.session_duration = False
                continue
            end = rec.logout_datetime or now
            seconds = max(0, int((end - start).total_seconds()))
            rec.session_duration_seconds = seconds
            rec.session_duration = _format_duration(seconds)

    @api.depends('presence_state', 'authentication_state')
    def _compute_presence_display(self):
        labels = dict(PRESENCE_SELECTION)
        icons = {
            'active': '🟢 Active / Using Odoo',
            'background': '🔵 Logged In / Background',
            'idle': '🟡 Idle',
            'inactive': '⚪ Inactive',
            'logged_out': '🔴 Logged Out',
        }
        for rec in self:
            rec.presence_display = icons.get(rec.presence_state) or labels.get(rec.presence_state)
            rec.authentication_display = (
                'Logged In' if rec.authentication_state == 'logged_in' else 'Logged Out'
            )

    @api.depends('user_id', 'user_id.name', 'browser', 'operating_system')
    def _compute_display_name(self):
        for rec in self:
            user_name = rec.user_id.name or rec.user_login or _('Unknown')
            device = ' / '.join(part for part in (rec.browser, rec.operating_system) if part) or _('Unknown device')
            rec.display_name = '%s — %s' % (user_name, device)

    @api.model
    def _presence_params(self):
        icp = self.env['ir.config_parameter'].sudo()
        return {
            'enabled': _param_bool(icp, PARAM_ENABLED, True),
            'heartbeat_seconds': _param_int(icp, PARAM_HEARTBEAT, 30, minimum=15, maximum=120),
            'idle_seconds': _param_int(icp, PARAM_IDLE_MINUTES, 5, minimum=1, maximum=180) * 60,
            'inactive_seconds': _param_int(icp, PARAM_INACTIVE_SECONDS, 90, minimum=30, maximum=3600),
            'track_portal': _param_bool(icp, PARAM_TRACK_PORTAL, False),
            'retention_days': _param_int(icp, PARAM_RETENTION_DAYS, 14, minimum=1, maximum=365),
        }

    @api.model
    def _client_presence_info(self):
        params = self._presence_params()
        identifier = False
        if request and getattr(request, 'session', None) and request.session.sid:
            identifier = request.session.sid[:42]
        return {
            'enabled': bool(params['enabled'] and self._should_track_user(self.env.user)),
            'heartbeat_seconds': params['heartbeat_seconds'],
            'idle_seconds': params['idle_seconds'],
            'session_identifier': identifier,
        }

    @api.model
    def _should_track_user(self, user=None):
        user = user or self.env.user
        if not user or not user.id or user.id == SUPERUSER_ID:
            return False
        if user._is_public():
            return False
        params = self._presence_params()
        if not params['enabled']:
            return False
        if user._is_internal():
            return True
        if params['track_portal'] and user.share:
            return True
        return False

    @api.model
    def _is_mobile_platform(self, platform):
        if not platform:
            return False
        return platform.lower() in {
            'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone', 'webos',
        }

    @api.model
    def _heartbeat_from_request(self, presence='active', visibility='visible', focused=True, interacted=False):
        if not request or not request.session or not request.session.uid or not request.session.sid:
            return {'status': 'ignored'}
        user = request.env.user
        if not self._should_track_user(user):
            return {'status': 'ignored', 'enabled': False}
        if request.env['ir.http'].is_a_bot():
            return {'status': 'ignored', 'bot': True}

        presence = presence if presence in CLIENT_PRESENCE else 'active'
        visibility = visibility if visibility in {'visible', 'hidden'} else 'unknown'
        focus_state = 'focused' if focused else 'blurred'
        user_agent = request.httprequest.user_agent
        return self.sudo()._apply_heartbeat(
            user=user,
            session_identifier=request.session.sid[:42],
            presence=presence,
            visibility=visibility,
            focus_state=focus_state,
            interacted=bool(interacted),
            company=request.env.company,
            ip_address=request.httprequest.remote_addr,
            browser=user_agent.browser or False,
            operating_system=user_agent.platform or False,
            user_agent=(user_agent.string or '')[:512],
        )

    @api.model
    def _apply_heartbeat(
        self,
        user,
        session_identifier,
        presence='active',
        visibility='unknown',
        focus_state='unknown',
        interacted=False,
        company=False,
        ip_address=False,
        browser=False,
        operating_system=False,
        user_agent=False,
        now=None,
    ):
        if not user or not session_identifier:
            return {'status': 'ignored'}
        now = now or fields.Datetime.now()
        params = self._presence_params()
        rec = self.search([
            ('session_identifier', '=', session_identifier),
            ('is_logged_in', '=', True),
        ], limit=1)
        device_type = 'mobile' if self._is_mobile_platform(operating_system) else 'computer'
        event = 'updated'
        if not rec:
            rec = self._create_logged_in_session(
                user=user,
                session_identifier=session_identifier,
                presence=presence,
                visibility=visibility,
                focus_state=focus_state,
                company=company,
                ip_address=ip_address,
                browser=browser,
                operating_system=operating_system,
                user_agent=user_agent,
                device_type=device_type,
                now=now,
            )
            event = 'login'
        else:
            skip_seconds = max(10, params['heartbeat_seconds'] // 2)
            last_hb = rec.last_heartbeat
            unchanged = (
                rec.presence_state == presence
                and rec.visibility_state == visibility
                and rec.focus_state == focus_state
                and not interacted
                and rec.company_id == (company or rec.company_id)
                and rec.ip_address == (ip_address or rec.ip_address)
                and last_hb
                and (now - last_hb).total_seconds() < skip_seconds
            )
            if unchanged:
                return {
                    'status': 'ok',
                    'id': rec.id,
                    'presence': rec.presence_state,
                    'skipped': True,
                }
            values = {
                'last_heartbeat': now,
                'presence_state': presence,
                'visibility_state': visibility,
                'focus_state': focus_state,
                'logout_datetime': False,
                'logout_reason': False,
            }
            if interacted or not rec.last_interaction:
                values['last_interaction'] = now
            if company:
                values['company_id'] = company.id
            if ip_address:
                values['ip_address'] = ip_address
            if browser:
                values['browser'] = browser
            if operating_system:
                values['operating_system'] = operating_system
            if user_agent:
                values['user_agent'] = user_agent
            values['device_type'] = device_type
            previous_state = rec.presence_state
            rec.write(values)
            if previous_state != rec.presence_state:
                event = 'presence'
        if event != 'updated':
            rec._notify_monitors(event)
        return {
            'status': 'ok',
            'id': rec.id,
            'presence': rec.presence_state,
            'authentication': rec.authentication_state,
        }

    @api.model
    def _create_logged_in_session(
        self,
        user,
        session_identifier,
        presence='active',
        visibility='unknown',
        focus_state='unknown',
        company=False,
        ip_address=False,
        browser=False,
        operating_system=False,
        user_agent=False,
        device_type='computer',
        now=None,
    ):
        now = now or fields.Datetime.now()
        vals = {
            'user_id': user.id,
            'session_identifier': session_identifier,
            'company_id': company.id if company else user.company_id.id,
            'login_datetime': now,
            'last_interaction': now,
            'last_heartbeat': now,
            'presence_state': presence if presence in CLIENT_PRESENCE else 'active',
            'visibility_state': visibility,
            'focus_state': focus_state,
            'ip_address': ip_address,
            'browser': browser,
            'operating_system': operating_system,
            'user_agent': user_agent,
            'device_type': device_type,
        }
        try:
            with self.env.cr.savepoint():
                rec = self.create(vals)
        except IntegrityError:
            rec = self.search([
                ('session_identifier', '=', session_identifier),
                ('is_logged_in', '=', True),
            ], limit=1)
            if rec:
                rec.write({
                    'last_heartbeat': now,
                    'presence_state': vals['presence_state'],
                    'visibility_state': visibility,
                    'focus_state': focus_state,
                    'user_id': user.id,
                })
                return rec
            raise
        return rec

    def _notify_monitors(self, event):
        group = self.env.ref('ages_user_presence.group_presence_monitor', raise_if_not_found=False)
        if not group:
            return
        Bus = self.env['bus.bus']
        for rec in self:
            Bus._sendone(group, CHANNEL_TYPE, {
                'id': rec.id,
                'user_id': rec.user_id.id,
                'session_identifier': rec.session_identifier,
                'presence_state': rec.presence_state,
                'authentication_state': rec.authentication_state,
                'is_logged_in': rec.is_logged_in,
                'event': event,
            })

    def _notify_force_logout(self):
        Bus = self.env['bus.bus']
        for rec in self:
            partner = rec.user_id.partner_id
            if partner:
                Bus._sendone(partner, FORCE_LOGOUT_TYPE, {
                    'session_identifier': rec.session_identifier,
                })

    def _mark_logged_out(self, reason='logout', now=None):
        now = now or fields.Datetime.now()
        online = self.filtered(lambda rec: rec.presence_state != 'logged_out')
        if not online:
            return
        online.write({
            'presence_state': 'logged_out',
            'logout_datetime': now,
            'logout_reason': reason,
            'last_heartbeat': now,
        })
        online._notify_monitors('logout')

    @api.model
    def _mark_identifier_logged_out(self, session_identifier, reason='logout'):
        if not session_identifier:
            return
        recs = self.search([
            ('session_identifier', '=', session_identifier),
            ('is_logged_in', '=', True),
        ])
        recs._mark_logged_out(reason=reason)

    @api.model
    def get_online_summary(self):
        self.check_access('read')
        sessions = self.search([('is_logged_in', '=', True)])
        counts = {'active': 0, 'background': 0, 'idle': 0, 'inactive': 0}
        for rec in sessions:
            if rec.presence_state in counts:
                counts[rec.presence_state] += 1
        return {
            'users_online': len(sessions.mapped('user_id')),
            'active_sessions': len(sessions),
            'active': counts['active'],
            'background': counts['background'],
            'idle': counts['idle'],
            'inactive': counts['inactive'],
        }

    def action_force_logout(self):
        if not self.env.user.has_group('ages_user_presence.group_presence_manager'):
            raise AccessError(_('Only presence managers can force logout.'))
        sessions = self.filtered(lambda rec: rec.is_logged_in)
        if not sessions:
            raise UserError(_('There is no logged-in session to terminate.'))
        identifiers = [ident for ident in sessions.mapped('session_identifier') if ident]
        if identifiers:
            try:
                root.session_store.delete_from_identifiers(identifiers)
            except Exception:
                _logger.exception('Could not delete HTTP sessions for presence force-logout')
        current_identifier = False
        if request and request.session and request.session.sid:
            current_identifier = request.session.sid[:42]
        hit_current = bool(current_identifier and current_identifier in identifiers)
        sessions._notify_force_logout()
        sessions._mark_logged_out(reason='force_logout')
        if hit_current:
            request.session.logout(keep_db=True)
        return True

    @api.model
    def _cron_refresh_presence(self):
        self._mark_stale_inactive()
        self._sync_missing_http_sessions()

    @api.model
    def _mark_stale_inactive(self):
        params = self._presence_params()
        deadline = fields.Datetime.now() - timedelta(seconds=params['inactive_seconds'])
        stale = self.search([
            ('is_logged_in', '=', True),
            ('presence_state', '!=', 'inactive'),
            ('last_heartbeat', '<', deadline),
        ])
        if stale:
            stale.write({'presence_state': 'inactive'})
            stale._notify_monitors('inactive')
            _logger.info('Marked %s presence session(s) inactive', len(stale))

    @api.model
    def _sync_missing_http_sessions(self):
        online = self.search_fetch(
            [('is_logged_in', '=', True)],
            ['session_identifier'],
        )
        identifiers = {rec.session_identifier for rec in online if rec.session_identifier}
        if not identifiers:
            return
        try:
            missing = root.session_store.get_missing_session_identifiers(identifiers)
        except Exception:
            _logger.debug('Could not inspect HTTP session store for presence cleanup', exc_info=True)
            return
        if not missing:
            return
        expired = online.filtered(lambda rec: rec.session_identifier in missing)
        expired._mark_logged_out(reason='expired')
        _logger.info('Presence: %s HTTP session(s) no longer exist', len(expired))

    @api.model
    def _cron_gc_presence(self):
        params = self._presence_params()
        cutoff = fields.Datetime.now() - timedelta(days=params['retention_days'])
        stale = self.search([
            ('is_logged_in', '=', False),
            ('logout_datetime', '!=', False),
            ('logout_datetime', '<', cutoff),
        ])
        count = len(stale)
        if count:
            stale.unlink()
            _logger.info('Presence GC removed %s logged-out session(s)', count)

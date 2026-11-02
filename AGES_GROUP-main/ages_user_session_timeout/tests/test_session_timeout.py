# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


def _sid(char):
    return (str(char) * 42)[:42]


@tagged('post_install', '-at_install')
class TestAgesSessionTimeout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Users = cls.env['res.users']
        cls.Session = cls.env['ages.user.session']
        cls.env['ir.config_parameter'].sudo().set_param('ages_user_session_timeout.enabled', 'True')
        cls.env['ir.config_parameter'].sudo().set_param('ages_user_session_timeout.idle_minutes', '15')
        cls.env['ir.config_parameter'].sudo().set_param('ages_user_session_timeout.warning_seconds', '60')
        cls.env['ir.config_parameter'].sudo().set_param('ages_user_session_timeout.apply_internal', 'True')
        cls.env['ir.config_parameter'].sudo().set_param('ages_user_session_timeout.exclude_admins', 'True')
        cls.ahmed = new_test_user(
            cls.env, login='timeout_ahmed', password='password',
            groups='base.group_user',
        )
        cls.ali = new_test_user(
            cls.env, login='timeout_ali', password='password',
            groups='base.group_user',
        )
        cls.usman = new_test_user(
            cls.env, login='timeout_usman', password='password',
            groups='base.group_user',
        )
        cls.manager = new_test_user(
            cls.env, login='timeout_manager', password='password',
            groups='base.group_user,ages_user_session_timeout.group_session_timeout_manager',
        )

    def _session(self, user, ident, **kwargs):
        now = fields.Datetime.now()
        vals = {
            'user_id': user.id,
            'session_identifier': ident,
            'login_datetime': now,
            'last_interaction': now,
            'last_heartbeat': now,
            'timeout_last_activity': now,
            'presence_state': 'active',
            'company_id': user.company_id.id,
        }
        vals.update(kwargs)
        return self.Session.create(vals)

    def test_default_internal_user_uses_settings_timeout(self):
        cfg = self.ahmed._ages_timeout_config()
        self.assertTrue(cfg['enabled'])
        self.assertEqual(cfg['idle_seconds'], 15 * 60)
        self.assertEqual(cfg['warning_seconds'], 60)

    def test_custom_timeout_per_user(self):
        self.ahmed.sudo().write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 30,
            'ages_timeout_warning_minutes': 5,
        })
        self.ali.sudo().write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 60,
            'ages_timeout_warning_minutes': 2,
        })
        self.usman.sudo().write({'ages_timeout_policy': 'disabled'})
        self.assertEqual(self.ahmed._ages_timeout_config()['idle_seconds'], 30 * 60)
        self.assertEqual(self.ahmed._ages_timeout_config()['warning_seconds'], 5 * 60)
        self.assertEqual(self.ali._ages_timeout_config()['idle_seconds'], 60 * 60)
        self.assertFalse(self.usman._ages_timeout_config()['enabled'])
        self.assertFalse(self.usman._ages_is_timeout_enforced())

    def test_disabled_user_status_always_valid(self):
        self.usman.sudo().write({'ages_timeout_policy': 'disabled'})
        old = fields.Datetime.now() - timedelta(hours=5)
        status = self.usman._ages_status_from_timestamps(old, old)
        self.assertTrue(status['valid'])
        self.assertFalse(status['enabled'])

    def test_activity_resets_remaining_time(self):
        self.ahmed.sudo().write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 15,
        })
        start = fields.Datetime.now() - timedelta(minutes=10)
        status = self.ahmed._ages_status_from_timestamps(start, start)
        self.assertTrue(status['valid'])
        self.assertGreater(status['remaining_seconds'], 4 * 60)
        expired = self.ahmed._ages_status_from_timestamps(
            fields.Datetime.now() - timedelta(minutes=16),
            fields.Datetime.now() - timedelta(minutes=16),
        )
        self.assertFalse(expired['valid'])
        self.assertEqual(expired['reason'], 'inactivity_timeout')
        reset = self.ahmed._ages_status_from_timestamps(
            fields.Datetime.now(),
            start,
        )
        self.assertTrue(reset['valid'])
        self.assertGreater(reset['remaining_seconds'], 14 * 60)

    def test_normal_user_cannot_change_own_policy(self):
        with self.assertRaises(AccessError):
            self.ahmed.with_user(self.ahmed).write({
                'ages_timeout_policy': 'disabled',
            })
        with self.assertRaises(AccessError):
            self.ahmed.with_user(self.ahmed).write({
                'ages_timeout_minutes': 120,
            })

    def test_manager_can_change_policy(self):
        self.ahmed.with_user(self.manager).write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 45,
            'ages_timeout_warning_minutes': 3,
        })
        self.assertEqual(self.ahmed.ages_timeout_policy, 'custom')
        self.assertEqual(self.ahmed.ages_timeout_minutes, 45)
        self.assertTrue(self.ahmed.ages_force_session_timeout)

    def test_multiple_sessions_expire_independently(self):
        self.ahmed.sudo().write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 15,
        })
        chrome = self._session(self.ahmed, _sid('C'))
        firefox = self._session(self.ahmed, _sid('F'))
        firefox.timeout_last_activity = fields.Datetime.now() - timedelta(minutes=20)
        firefox.last_interaction = firefox.timeout_last_activity
        self.Users._cron_expire_idle_sessions()
        self.assertEqual(firefox.presence_state, 'logged_out')
        self.assertEqual(firefox.logout_reason, 'inactivity_timeout')
        self.assertEqual(chrome.presence_state, 'active')
        self.assertTrue(chrome.is_logged_in)

    def test_cron_does_not_expire_disabled_user(self):
        self.usman.sudo().write({'ages_timeout_policy': 'disabled'})
        rec = self._session(self.usman, _sid('U'))
        rec.timeout_last_activity = fields.Datetime.now() - timedelta(hours=3)
        rec.last_interaction = rec.timeout_last_activity
        self.Users._cron_expire_idle_sessions()
        self.assertEqual(rec.presence_state, 'active')

    def test_custom_user_times_out_when_global_default_is_off(self):
        self.env['ir.config_parameter'].sudo().set_param('ages_user_session_timeout.enabled', 'False')
        self.ahmed.sudo().write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 15,
        })
        self.ali.sudo().write({'ages_timeout_policy': 'default'})
        self.assertTrue(self.ahmed._ages_is_timeout_enforced())
        self.assertFalse(self.ali._ages_is_timeout_enforced())

    def test_presence_timeout_at_matches_last_activity(self):
        self.ahmed.sudo().write({
            'ages_timeout_policy': 'custom',
            'ages_timeout_minutes': 15,
        })
        rec = self._session(self.ahmed, _sid('T'))
        self.assertTrue(rec.timeout_enabled)
        self.assertEqual(rec.timeout_minutes, 15)
        self.assertTrue(rec.timeout_at)
        expected = rec.timeout_last_activity + timedelta(minutes=15)
        self.assertEqual(rec.timeout_at, expected)

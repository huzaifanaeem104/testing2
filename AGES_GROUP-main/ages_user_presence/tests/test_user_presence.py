# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


def _sid(char):
    return (str(char) * 42)[:42]


@tagged('post_install', '-at_install')
class TestAgesUserPresence(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Session = cls.env['ages.user.session']
        cls.internal = new_test_user(
            cls.env,
            login='presence_internal',
            password='password',
            groups='base.group_user',
        )
        cls.other = new_test_user(
            cls.env,
            login='presence_other',
            password='password',
            groups='base.group_user',
        )
        cls.monitor = new_test_user(
            cls.env,
            login='presence_monitor',
            password='password',
            groups='base.group_user,ages_user_presence.group_presence_monitor',
        )
        cls.manager = new_test_user(
            cls.env,
            login='presence_manager',
            password='password',
            groups='base.group_user,ages_user_presence.group_presence_manager',
        )

    def _beat(self, user, ident, **kwargs):
        values = {
            'user': user,
            'session_identifier': ident,
            'presence': 'active',
            'visibility': 'visible',
            'focus_state': 'focused',
            'interacted': True,
            'company': user.company_id,
            'ip_address': '10.0.0.8',
            'browser': 'chrome',
            'operating_system': 'linux',
        }
        values.update(kwargs)
        return self.Session._apply_heartbeat(**values)

    def test_a_active_visible_focused(self):
        result = self._beat(self.internal, _sid('A'))
        rec = self.Session.browse(result['id'])
        self.assertEqual(rec.presence_state, 'active')
        self.assertEqual(rec.authentication_state, 'logged_in')
        self.assertTrue(rec.is_logged_in)
        self.assertIn('Using Odoo', rec.presence_display)
        self.assertEqual(rec.authentication_display, 'Logged In')

    def test_b_hidden_tab_is_background(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('B'))['id'])
        self._beat(
            self.internal,
            _sid('B'),
            presence='background',
            visibility='hidden',
            focus_state='blurred',
            interacted=False,
        )
        self.assertEqual(rec.presence_state, 'background')
        self.assertEqual(rec.authentication_state, 'logged_in')
        self.assertIn('Background', rec.presence_display)

    def test_c_unfocused_visible_is_background(self):
        rec = self.Session.browse(self._beat(
            self.internal,
            _sid('C'),
            presence='background',
            visibility='visible',
            focus_state='blurred',
        )['id'])
        self.assertEqual(rec.presence_state, 'background')
        self.assertTrue(rec.is_logged_in)

    def test_d_idle_when_visible_without_interaction(self):
        rec = self.Session.browse(self._beat(
            self.internal,
            _sid('D'),
            presence='idle',
            visibility='visible',
            focus_state='focused',
            interacted=False,
        )['id'])
        self.assertEqual(rec.presence_state, 'idle')
        self.assertTrue(rec.is_logged_in)

    def test_e_return_to_active(self):
        ident = _sid('E')
        rec = self.Session.browse(self._beat(
            self.internal, ident, presence='idle', interacted=False,
        )['id'])
        self._beat(self.internal, ident, presence='active', interacted=True)
        self.assertEqual(rec.presence_state, 'active')

    def test_f_logout_leaves_online_list(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('F'))['id'])
        rec._mark_logged_out(reason='logout')
        self.assertEqual(rec.presence_state, 'logged_out')
        self.assertFalse(rec.is_logged_in)
        self.assertTrue(rec.logout_datetime)
        online = self.Session.search([('is_logged_in', '=', True), ('id', '=', rec.id)])
        self.assertFalse(online)

    def test_g_missed_heartbeat_becomes_inactive_not_logged_out(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('G'))['id'])
        rec.write({
            'last_heartbeat': fields.Datetime.now() - timedelta(seconds=180),
        })
        self.Session._mark_stale_inactive()
        self.assertEqual(rec.presence_state, 'inactive')
        self.assertTrue(rec.is_logged_in)

    def test_h_multiple_sessions_are_independent(self):
        chrome = self.Session.browse(self._beat(
            self.internal, _sid('H'), browser='chrome', presence='active',
        )['id'])
        firefox = self.Session.browse(self._beat(
            self.internal, _sid('I'), browser='firefox', presence='background',
            visibility='hidden', focus_state='blurred',
        )['id'])
        self.assertNotEqual(chrome.id, firefox.id)
        self.assertEqual(chrome.user_id, firefox.user_id)
        self.assertEqual(chrome.presence_state, 'active')
        self.assertEqual(firefox.presence_state, 'background')
        summary = self.Session.get_online_summary()
        self.assertGreaterEqual(summary['users_online'], 1)
        self.assertGreaterEqual(summary['active_sessions'], 2)

    def test_i_heartbeat_does_not_log_out(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('J'))['id'])
        rec.write({'last_heartbeat': fields.Datetime.now() - timedelta(seconds=45)})
        self.Session._mark_stale_inactive()
        self.assertEqual(rec.presence_state, 'active')
        self.assertTrue(rec.is_logged_in)

    def test_j_ordinary_user_cannot_read_sessions(self):
        self._beat(self.internal, _sid('K'))
        with self.assertRaises(AccessError):
            self.Session.with_user(self.internal).search([])
        with self.assertRaises(AccessError):
            self.Session.with_user(self.internal).get_online_summary()

    def test_monitor_can_read_but_not_force_logout(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('L'))['id'])
        seen = self.Session.with_user(self.monitor).search([('id', '=', rec.id)])
        self.assertEqual(seen, rec)
        with self.assertRaises(AccessError):
            rec.with_user(self.monitor).action_force_logout()

    def test_manager_force_logout(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('M'))['id'])
        rec.with_user(self.manager).action_force_logout()
        self.assertEqual(rec.presence_state, 'logged_out')
        self.assertEqual(rec.logout_reason, 'force_logout')
        self.assertFalse(rec.is_logged_in)

    def test_summary_counts_users_and_sessions(self):
        self._beat(self.internal, _sid('N'), presence='active')
        self._beat(self.internal, _sid('O'), presence='idle', interacted=False)
        self._beat(self.other, _sid('P'), presence='background', visibility='hidden', focus_state='blurred')
        summary = self.Session.get_online_summary()
        self.assertEqual(summary['users_online'], 2)
        self.assertEqual(summary['active_sessions'], 3)
        self.assertEqual(summary['active'], 1)
        self.assertEqual(summary['idle'], 1)
        self.assertEqual(summary['background'], 1)

    def test_interaction_updates_last_interaction_only_when_flagged(self):
        rec = self.Session.browse(self._beat(self.internal, _sid('Q'), interacted=True)['id'])
        rec.write({
            'last_interaction': fields.Datetime.now() - timedelta(minutes=5),
            'last_heartbeat': fields.Datetime.now() - timedelta(seconds=20),
        })
        first = rec.last_interaction
        self._beat(
            self.internal,
            _sid('Q'),
            presence='active',
            interacted=False,
        )
        self.assertEqual(rec.last_interaction, first)
        self._beat(self.internal, _sid('Q'), presence='active', interacted=True)
        self.assertGreater(rec.last_interaction, first)

    def test_gc_removes_old_logged_out_only(self):
        live = self.Session.browse(self._beat(self.internal, _sid('R'))['id'])
        dead = self.Session.browse(self._beat(self.other, _sid('S'))['id'])
        dead._mark_logged_out(reason='logout')
        dead.logout_datetime = fields.Datetime.now() - timedelta(days=30)
        self.env['ir.config_parameter'].sudo().set_param('ages_user_presence.retention_days', '14')
        self.Session._cron_gc_presence()
        self.assertTrue(live.exists())
        self.assertFalse(dead.exists())

    def test_superuser_and_public_are_not_tracked(self):
        public = self.env.ref('base.public_user')
        self.assertFalse(self.Session._should_track_user(public))
        self.assertFalse(self.Session._should_track_user(self.env.ref('base.user_root')))
        self.assertTrue(self.Session._should_track_user(self.internal))

    def test_same_identifier_reuses_row(self):
        first = self._beat(self.internal, _sid('T'))
        second = self._beat(self.internal, _sid('T'), presence='idle', interacted=False)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(self.Session.search_count([('session_identifier', '=', _sid('T'))]), 1)

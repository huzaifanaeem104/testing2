from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MilkingCommon


@tagged('post_install', '-at_install', 'dairy')
class TestMilking(MilkingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cows = cls._create_cows(50)
        cls.dry_cow = cls._create_cows(1, prefix='T-DRY', lactating=False)

    def test_three_sessions_fifty_cows(self):
        today = fields.Date.today()
        sessions = self.env['dairy.milking.session']
        for shift, qty in ((self.shift_morning, 6.5), (self.shift_afternoon, 4.0), (self.shift_evening, 5.25)):
            sessions |= self._milk_session(self.cows, shift, today, qty, user=self.user_milker)
        self.assertEqual(len(sessions), 3)
        for session in sessions:
            self.assertEqual(session.expected_count, 50, 'Dry cow must not be loaded')
            self.assertEqual(session.state, 'confirmed')
            self.assertAlmostEqual(session.total_liters, sum(session.line_ids.mapped('quantity_liters')))
            self.assertAlmostEqual(session.saleable_liters, session.total_liters)
        self.assertAlmostEqual(sum(sessions.mapped('total_liters')), 50 * (6.5 + 4.0 + 5.25))
        self.assertAlmostEqual(sessions.filtered(lambda s: s.shift == 'morning').average_liters, 6.5)
        # loading again is idempotent
        self.assertEqual(len(self.env['dairy.milking.line'].search([('date', '=', today)])), 150)

    def test_duplicate_session_rejected(self):
        self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id})
        with self.assertRaises(ValidationError), mute_logger('odoo.sql_db'):
            with self.cr.savepoint():
                self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id})

    def test_cancelled_session_can_be_recreated(self):
        session = self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id, 'cancel_reason': 'Wrong'})
        session.with_user(self.user_manager).action_cancel()
        self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id})

    def test_line_validations(self):
        session = self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id})
        cow = self.cows[0]
        self.env['dairy.milking.line'].create({'session_id': session.id, 'animal_id': cow.id, 'quantity_liters': 5})
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env['dairy.milking.line'].create({'session_id': session.id, 'animal_id': cow.id, 'quantity_liters': 3})
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env['dairy.milking.line'].create({
                    'session_id': session.id, 'animal_id': self.cows[1].id,
                    'entry_status': 'recorded', 'quantity_liters': -2})
        with self.assertRaises(ValidationError):
            self.env['dairy.milking.line'].create({
                'session_id': session.id, 'animal_id': self.dry_cow.id, 'quantity_liters': 4})
        with self.assertRaises(ValidationError):
            self.env['dairy.milking.line'].create({
                'session_id': session.id, 'animal_id': self.cows[2].id, 'entry_status': 'recorded'})
        # an ineligible animal can still be documented as missed
        self.env['dairy.milking.line'].create({
            'session_id': session.id, 'animal_id': self.dry_cow.id, 'entry_status': 'missed', 'remarks': 'Dry'})

    def test_missing_vs_zero(self):
        session = self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id})
        session.action_load_animals()
        lines = session.line_ids
        lines[:47].write({'quantity_liters': 8})
        lines[47].write({'entry_status': 'zero'})
        lines[48].write({'entry_status': 'missed', 'remarks': 'Lame'})
        self.assertEqual(session.pending_count, 1)
        with self.assertRaises(UserError):
            session.action_submit()
        lines[49].write({'entry_status': 'zero'})
        session.action_submit()
        self.assertEqual((session.recorded_count, session.zero_count, session.missed_count), (47, 2, 1))
        self.assertAlmostEqual(session.total_liters, 47 * 8)

    def test_confirmation_permissions_and_lock(self):
        session = self._milk_session(self.cows, self.shift_morning, user=self.user_milker, confirm=False)
        with self.assertRaises(AccessError):
            session.with_user(self.user_milker).action_confirm()
        # submitted session is locked for the operator
        with self.assertRaises(UserError):
            session.line_ids[0].with_user(self.user_milker).write({'quantity_liters': 1})
        session.with_user(self.user_manager).action_confirm()
        with self.assertRaises(UserError):
            session.line_ids[0].with_user(self.user_manager).write({'quantity_liters': 1})
        with self.assertRaises(UserError):
            session.with_user(self.user_manager).write({'date': fields.Date.today() - timedelta(days=1)})
        with self.assertRaises(UserError):
            session.unlink()
        # the bypass context cannot be abused by operators
        with self.assertRaises(UserError):
            session.line_ids[0].with_user(self.user_milker).with_context(
                dairy_milking_correction=True).write({'quantity_liters': 1})

    def test_correction_preserves_audit(self):
        session = self._milk_session(self.cows, self.shift_morning, qty=10)
        line = session.line_ids[0]
        correction = self.env['dairy.milking.correction'].with_user(self.user_milker).create({
            'session_id': session.id, 'line_id': line.id,
            'new_entry_status': 'recorded', 'new_quantity': 12.5, 'reason': 'Meter misread'})
        self.assertEqual(correction.old_quantity, 10)
        with self.assertRaises(AccessError):
            correction.with_user(self.user_milker).action_apply()
        correction.with_user(self.user_manager).action_apply()
        self.assertEqual(line.quantity_liters, 12.5)
        self.assertAlmostEqual(session.total_liters, 49 * 10 + 12.5)
        self.assertEqual(correction.state, 'applied')
        with self.assertRaises(UserError):
            correction.unlink()
        with self.assertRaises(UserError):
            correction.with_user(self.user_manager).action_apply()

    def test_cancel_confirmed_session(self):
        session = self._milk_session(self.cows, self.shift_morning)
        with self.assertRaises(UserError):
            session.with_user(self.user_manager).action_cancel()  # no reason
        session.with_user(self.user_manager).write({'cancel_reason': 'Recorded on the wrong date'})
        session.with_user(self.user_manager).action_cancel()
        self.assertEqual(session.state, 'cancelled')
        self.assertEqual(len(session.line_ids), 50, 'Records are kept for audit')

    def test_withdrawal_withholds_milk(self):
        cow = self.cows[0]
        today = fields.Date.today()
        session = self._milk_session(self.cows, self.shift_morning, today, qty=10, confirm=True)
        line = session.line_ids.filtered(lambda l: l.animal_id == cow)
        self.assertEqual(line.milk_destination, 'saleable')
        # a backdated restriction created by the vet reclassifies recorded milk
        self.env['dairy.milk.withdrawal'].with_user(self.user_vet).create({
            'animal_id': cow.id, 'start_date': today, 'end_date': today + timedelta(days=4),
            'reason': 'Oxytetracycline'})
        self.assertEqual(line.milk_destination, 'withheld')
        self.assertAlmostEqual(session.withheld_liters, 10)
        self.assertAlmostEqual(session.saleable_liters, 490)

    def test_quality_discard(self):
        session = self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id})
        line = self.env['dairy.milking.line'].create({
            'session_id': session.id, 'animal_id': self.cows[0].id, 'quantity_liters': 4, 'quality_status': 'colostrum'})
        self.assertEqual(line.milk_destination, 'discarded')
        self.assertEqual(session.saleable_liters, 0)

    def test_future_session_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['dairy.milking.session'].create({
                'shift_id': self.shift_morning.id, 'date': fields.Date.today() + timedelta(days=1)})

    def test_yield_decline_alert(self):
        cow = self.cows[0]
        today = fields.Date.today()
        for day in range(14):
            date = today - timedelta(days=day)
            session = self.env['dairy.milking.session'].create({'shift_id': self.shift_morning.id, 'date': date})
            self.env['dairy.milking.line'].create({
                'session_id': session.id, 'animal_id': cow.id, 'quantity_liters': 5 if day < 7 else 10})
            session.action_submit()
        self.env['dairy.animal']._cron_update_yield_trends()
        self.env['dairy.animal']._cron_update_yield_trends()
        self.assertTrue(cow.yield_decline_alert)
        self.assertAlmostEqual(cow.yield_decline_pct, -50)
        self.assertEqual(len(cow.activity_ids), 1)

    def test_session_reminder_cron_idempotent(self):
        Session = self.env['dairy.milking.session']
        Session._cron_session_reminders()
        count = Session.search_count([])
        Session._cron_session_reminders()
        self.assertEqual(Session.search_count([]), count)
        yesterday = fields.Date.today() - timedelta(days=1)
        self.assertEqual(Session.search_count([('date', '=', yesterday)]), 3)

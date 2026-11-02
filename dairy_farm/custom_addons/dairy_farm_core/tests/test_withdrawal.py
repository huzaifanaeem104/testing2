from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import DairyCommon


@tagged('post_install', '-at_install', 'dairy')
class TestMilkWithdrawal(DairyCommon):

    def test_restriction_lifecycle(self):
        cow = self._create_cows(1)
        today = fields.Date.today()
        wd = self.env['dairy.milk.withdrawal'].create({
            'animal_id': cow.id, 'start_date': today - timedelta(days=2),
            'end_date': today + timedelta(days=3), 'reason': 'Antibiotic treatment'})
        Withdrawal = self.env['dairy.milk.withdrawal']
        self.assertTrue(cow.has_active_withdrawal)
        self.assertEqual(Withdrawal._restricted_animals(cow, today), cow)
        # the planned end date passing does not release the milk
        self.assertEqual(Withdrawal._restricted_animals(cow, today + timedelta(days=10)), cow)
        # cannot release before the end of the withdrawal period
        with self.assertRaises(ValidationError):
            wd.with_user(self.user_vet)._do_release(today, 'Test negative')
        # operators cannot release
        with self.assertRaises(AccessError):
            wd.with_user(self.user_milker)._do_release(today + timedelta(days=3), 'x')
        wd.with_user(self.user_vet)._do_release(today + timedelta(days=3), 'Residue test negative', 'LAB-1')
        self.assertEqual(wd.state, 'released')
        self.assertEqual(Withdrawal._restricted_animals(cow, today + timedelta(days=2)), cow)
        self.assertFalse(Withdrawal._restricted_animals(cow, today + timedelta(days=3)))
        with self.assertRaises(UserError):
            wd.end_date = today
        with self.assertRaises(UserError):
            wd.unlink()

    def test_cron_idempotent(self):
        cow = self._create_cows(1)
        today = fields.Date.today()
        wd = self.env['dairy.milk.withdrawal'].create({
            'animal_id': cow.id, 'start_date': today - timedelta(days=5),
            'end_date': today - timedelta(days=1), 'reason': 'Mastitis'})
        Withdrawal = self.env['dairy.milk.withdrawal']
        Withdrawal._cron_withdrawal_alerts()
        Withdrawal._cron_withdrawal_alerts()
        self.assertEqual(len(wd.activity_ids), 1)

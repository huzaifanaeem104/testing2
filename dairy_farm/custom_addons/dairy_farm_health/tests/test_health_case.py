from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import HealthCommon


@tagged('post_install', '-at_install')
class TestHealthCase(HealthCommon):

    def test_case_lifecycle(self):
        case = self._new_case()
        self.assertTrue(case.name.startswith('HC/'))
        with self.assertRaises(UserError):
            case.action_diagnose()  # no diagnosis yet
        case.diagnosis = 'Clinical mastitis, front-left quarter'
        case.action_diagnose()
        self.assertEqual(case.state, 'diagnosed')
        with self.assertRaises(UserError):
            case.action_close()  # outcome required
        case.outcome = 'recovered'
        case.action_close()
        self.assertEqual(case.state, 'closed')
        self.assertTrue(case.closed_date)
        case.action_reopen()
        self.assertEqual(case.state, 'diagnosed')

    def test_close_blocked_by_pending_work(self):
        case = self._new_case(diagnosis='Lameness', condition='lameness')
        case.action_diagnose()
        self.env['dairy.treatment'].create({'case_id': case.id, 'description': 'Hoof trimming'})
        case.outcome = 'recovered'
        with self.assertRaises(UserError):
            case.action_close()
        case.treatment_ids.action_cancel()
        followup = self.env['dairy.health.followup'].create({'case_id': case.id, 'date': date.today() + timedelta(days=3)})
        self.assertTrue(followup.activity_ids, 'follow-up schedules an activity')
        with self.assertRaises(UserError):
            case.action_close()
        with self.assertRaises(UserError):
            followup.action_done()  # result required
        followup.result = 'recovered'
        followup.action_done()
        self.assertFalse(followup.activity_ids.filtered(lambda a: a.summary == followup._due_summary()))
        case.action_close()
        self.assertEqual(case.state, 'closed')

    def test_urgent_case_alert_and_overdue_followup_cron_idempotent(self):
        case = self._new_case(severity='critical')
        self.assertTrue(case.activity_ids)
        followup = self.env['dairy.health.followup'].create({'case_id': case.id, 'date': date.today() - timedelta(days=2)})
        Followup = self.env['dairy.health.followup']
        Followup._cron_overdue_followups()
        Followup._cron_overdue_followups()
        overdue = followup.activity_ids.filtered(lambda a: a.summary == followup._overdue_summary())
        self.assertEqual(len(overdue), 1)
        followup.result = 'improving'
        followup.action_done()
        self.assertFalse(followup.activity_ids, 'due and overdue alerts are both resolved')
        with self.assertRaises(UserError):
            followup.action_cancel()
        case.write({'diagnosis': 'Acute mastitis', 'outcome': 'recovered'})
        case.action_diagnose()
        case.action_close()
        self.assertFalse(case.activity_ids.filtered(lambda a: a.summary == case._urgent_summary()))

    def test_cancel_and_reopen_guards(self):
        case = self._new_case(diagnosis='Bloat', condition='digestive')
        case.action_diagnose()
        treatment = self.env['dairy.treatment'].create({'case_id': case.id, 'description': 'Drench'})
        followup = self.env['dairy.health.followup'].create({'case_id': case.id, 'date': date.today()})
        with self.assertRaises(UserError):
            case.action_reopen()  # not closed
        case.action_cancel()
        self.assertEqual(case.state, 'cancelled')
        self.assertEqual(treatment.state, 'cancelled')
        self.assertEqual(followup.state, 'cancelled')
        closed = self._new_case(diagnosis='Fever', outcome='recovered')
        closed.action_diagnose()
        closed.action_close()
        with self.assertRaises(UserError):
            closed.action_cancel()

    def test_diagnosed_case_cannot_be_deleted(self):
        case = self._new_case(diagnosis='Fever')
        case.action_diagnose()
        with self.assertRaises(UserError):
            case.unlink()

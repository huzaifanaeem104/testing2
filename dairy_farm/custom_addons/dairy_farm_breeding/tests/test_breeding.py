from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.dairy_farm_core.tests.common import DairyCommon


@tagged('post_install', '-at_install', 'dairy')
class TestBreeding(DairyCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cow = cls._create_cows(1)
        cls.today = fields.Date.today()
        cls.Event = cls.env['dairy.breeding.event'].with_user(cls.user_vet)

    def _breed(self, days_ago=40):
        heat = self.Event.create({'animal_id': self.cow.id, 'event_type': 'heat',
                                  'heat_date': self.today - timedelta(days=days_ago), 'heat_signs': 'standing'})
        heat.action_done()
        service = self.Event.create({'animal_id': self.cow.id, 'event_type': 'breeding', 'heat_event_id': heat.id,
                                     'breeding_date': self.today - timedelta(days=days_ago), 'method': 'ai',
                                     'sire_id': self.bull.id, 'semen_reference': 'STRAW-001'})
        service.action_done()
        return heat, service

    def _check(self, service, result):
        check = self.env['dairy.pregnancy.check'].with_user(self.user_vet).create({
            'animal_id': self.cow.id, 'breeding_event_id': service.id, 'result': result, 'date': self.today})
        check.action_done()
        return check

    def test_breeding_does_not_make_pregnant(self):
        heat, service = self._breed()
        self.assertEqual(self.cow.last_heat_date, heat.heat_date)
        self.assertEqual(self.cow.reproductive_status, 'inseminated')
        self.assertEqual(service.result, 'pending')
        self.assertEqual(service.service_number, 1)
        self.assertEqual(service.pregnancy_check_due, service.breeding_date + timedelta(days=35))
        self.assertTrue(service.activity_ids, 'Pregnancy check reminder scheduled')

    def test_pregnancy_confirmed_only_by_examination(self):
        _heat, service = self._breed(days_ago=40)
        check = self._check(service, 'pregnant')
        self.assertEqual(self.cow.reproductive_status, 'pregnant')
        self.assertEqual(service.result, 'pregnant')
        self.assertEqual(check.expected_calving_date, service.breeding_date + timedelta(days=283))
        self.assertEqual(self.cow.expected_calving_date, check.expected_calving_date)
        self.assertFalse(service.activity_ids, 'Reminder resolved')
        # cannot be bred again while pregnant
        again = self.Event.create({'animal_id': self.cow.id, 'event_type': 'breeding',
                                   'breeding_date': self.today, 'method': 'ai'})
        with self.assertRaises(UserError):
            again.action_done()
        with self.assertRaises(UserError):
            check.write({'result': 'open'})

    def test_failed_and_repeat_breeding(self):
        _heat, first = self._breed(days_ago=60)
        self._check(first, 'open')
        self.assertEqual(first.result, 'open')
        self.assertEqual(self.cow.reproductive_status, 'open')
        _heat, second = self._breed(days_ago=20)
        self.assertEqual(second.service_number, 2)
        self.assertEqual(self.cow.reproductive_status, 'inseminated')

    def test_pregnancy_loss(self):
        _heat, service = self._breed(days_ago=80)
        self._check(service, 'pregnant')
        self._check(service, 'open')
        self.assertEqual(service.result, 'lost')
        self.assertEqual(self.cow.reproductive_status, 'open')
        self.assertFalse(self.cow.expected_calving_date)

    def test_calving_registers_twins(self):
        _heat, service = self._breed(days_ago=290)
        self._check(service, 'pregnant')
        lactations = self.cow.lactation_number
        calving = self.env['dairy.calving.event'].with_user(self.user_vet).create({
            'dam_id': self.cow.id, 'breeding_event_id': service.id, 'calving_date': self.today,
            'outcome': 'live', 'calving_ease': 'assisted',
            'calf_line_ids': [(0, 0, {'tag_number': 'T-CALF-A', 'gender': 'female', 'birth_weight': 28}),
                              (0, 0, {'tag_number': 'T-CALF-B', 'gender': 'male', 'birth_weight': 30}),
                              (0, 0, {'gender': 'male', 'status': 'dead', 'notes': 'Stillborn triplet'})],
        })
        self.assertEqual(calving.sire_id, self.bull)
        calving.action_done()
        calves = calving.calf_line_ids.calf_id
        self.assertEqual(len(calves), 2)
        for calf in calves:
            self.assertEqual(calf.dam_id, self.cow)
            self.assertEqual(calf.sire_id, self.bull)
            self.assertEqual(calf.acquisition_type, 'born')
            self.assertEqual(calf.birth_date, self.today)
        self.assertEqual(self.cow.lactation_number, lactations + 1)
        self.assertEqual(self.cow.last_calving_date, self.today)
        self.assertEqual(self.cow.production_status, 'lactating')
        self.assertEqual(self.cow.reproductive_status, 'open')
        self.assertEqual(service.result, 'calved')
        self.assertEqual(self.cow.offspring_count, 2)
        with self.assertRaises(UserError):
            calving.action_done()
        self.assertEqual(len(calving.calf_line_ids.calf_id), 2, 'No duplicate calves')

    def test_abortion(self):
        _heat, service = self._breed(days_ago=150)
        self._check(service, 'pregnant')
        calving = self.env['dairy.calving.event'].with_user(self.user_vet).create({
            'dam_id': self.cow.id, 'breeding_event_id': service.id, 'outcome': 'abortion', 'start_lactation': False})
        calving.action_done()
        self.assertEqual(service.result, 'lost')
        self.assertEqual(self.cow.reproductive_status, 'open')

    def test_validations_and_security(self):
        with self.assertRaises(ValidationError):
            self.Event.create({'animal_id': self.bull.id, 'event_type': 'heat'})
        with self.assertRaises(ValidationError):
            self.Event.create({'animal_id': self.cow.id, 'event_type': 'breeding',
                               'breeding_date': self.today + timedelta(days=2), 'method': 'ai'})
        with self.assertRaises(AccessError):
            self.env['dairy.breeding.event'].with_user(self.user_milker).create({
                'animal_id': self.cow.id, 'event_type': 'heat'})
        with self.assertRaises(AccessError):
            self.env['dairy.breeding.event'].with_user(self.user_accountant).create({
                'animal_id': self.cow.id, 'event_type': 'heat'})

    def test_alert_cron_idempotent(self):
        _heat, service = self._breed(days_ago=290)
        self._check(service, 'pregnant')
        Event = self.env['dairy.breeding.event']
        Event._cron_breeding_alerts()
        Event._cron_breeding_alerts()
        summaries = self.cow.activity_ids.mapped('summary')
        self.assertEqual(summaries.count('Expected calving'), 1)
        self.assertEqual(summaries.count('Dry-off due'), 1)

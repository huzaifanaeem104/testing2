from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import DairyCommon


@tagged('post_install', '-at_install', 'dairy')
class TestDairyAnimal(DairyCommon):

    def test_create_animal_sequence(self):
        cow = self._create_cows(1)
        self.assertTrue(cow.name.startswith('ANM/'))
        self.assertEqual(cow.display_name, 'T-COW-001')
        self.assertTrue(cow.is_milking_eligible)
        self.assertIn(cow, self.env['dairy.animal'].search([('is_milking_eligible', '=', True)]))

    def test_duplicate_tag_rejected(self):
        self._create_cows(1)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env['dairy.animal'].create({'tag_number': 'T-COW-001', 'animal_type': 'cow'})

    def test_calf_linked_to_dam(self):
        cow = self._create_cows(1)
        calf = self.env['dairy.animal'].create({
            'tag_number': 'T-CALF-1', 'animal_type': 'calf', 'gender': 'female',
            'acquisition_type': 'born', 'birth_date': '2025-01-10',
            'dam_id': cow.id, 'sire_id': self.bull.id})
        self.assertEqual(calf.production_status, 'growing')
        self.assertIn(calf, cow.offspring_ids)
        self.assertEqual(cow.offspring_count, 1)
        self.assertEqual(self.bull.offspring_count, 1)

    def test_invalid_parentage(self):
        cow = self._create_cows(1)
        with self.assertRaises(ValidationError):
            self.env['dairy.animal'].create({
                'tag_number': 'T-CALF-X', 'animal_type': 'calf', 'birth_date': '2024-01-01',
                'dam_id': self.bull.id})
        with self.assertRaises(ValidationError):
            self.env['dairy.animal'].create({
                'tag_number': 'T-CALF-Y', 'animal_type': 'calf', 'birth_date': '2019-01-01',
                'dam_id': cow.id})  # calf born before its dam
        with self.assertRaises(ValidationError):
            self.env['dairy.animal'].create({'tag_number': 'T-BAD', 'animal_type': 'bull', 'gender': 'female'})

    def test_archive_keeps_history(self):
        cow = self._create_cows(1)
        calf = self.env['dairy.animal'].create({
            'tag_number': 'T-CALF-2', 'animal_type': 'calf', 'birth_date': '2025-02-01', 'dam_id': cow.id})
        wizard = self.env['dairy.animal.exit.wizard'].create({
            'animal_id': cow.id, 'exit_type': 'sold', 'exit_reason': 'Low yield', 'sale_price': 150000})
        wizard.action_confirm()
        self.assertFalse(cow.active)
        self.assertEqual(cow.active_status, 'sold')
        self.assertEqual(cow.production_status, 'na')
        self.assertFalse(cow.is_milking_eligible)
        # history kept and still reachable
        self.assertEqual(calf.dam_id, cow)
        self.assertTrue(self.env['dairy.animal'].with_context(active_test=False).search([('id', '=', cow.id)]))
        with self.assertRaises(ValidationError):
            self.env['dairy.animal'].create({'tag_number': 'T-SOLD', 'animal_type': 'cow', 'active_status': 'sold'})

    def test_dry_off_and_lactation(self):
        cow = self._create_cows(1)
        cow.action_dry_off()
        self.assertEqual(cow.production_status, 'dry')
        self.assertFalse(cow.is_milking_eligible)
        cow.action_start_lactation()
        self.assertTrue(cow.is_milking_eligible)

    def test_herd_of_fifty(self):
        cows = self._create_cows(50)
        self.assertEqual(len(cows), 50)
        self.assertEqual(self.group_lactating.animal_count, 50)
        self.assertEqual(len(set(cows.mapped('name'))), 50)

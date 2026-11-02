from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import DairyCommon


@tagged('post_install', '-at_install', 'dairy')
class TestCoreSecurity(DairyCommon):

    def test_operator_cannot_edit_registry(self):
        cow = self._create_cows(1)
        for user in (self.user_milker, self.user_feeder, self.user_sales, self.user_accountant):
            self.assertEqual(cow.with_user(user).tag_number, 'T-COW-001')
            with self.assertRaises(AccessError):
                cow.with_user(user).write({'nickname': 'x'})
            with self.assertRaises(AccessError):
                self.env['dairy.animal'].with_user(user).create({'tag_number': 'NOPE', 'animal_type': 'cow'})

    def test_only_admin_deletes(self):
        cow = self._create_cows(1)
        with self.assertRaises(AccessError):
            cow.with_user(self.user_manager).unlink()
        cow.with_user(self.user_admin_dairy).unlink()

    def test_vet_and_manager_can_create(self):
        self.env['dairy.animal'].with_user(self.user_vet).create({'tag_number': 'V-1', 'animal_type': 'calf'})
        self.env['dairy.animal'].with_user(self.user_manager).create({'tag_number': 'M-1', 'animal_type': 'cow'})

    def test_restriction_write_rights(self):
        cow = self._create_cows(1)
        with self.assertRaises(AccessError):
            self.env['dairy.milk.withdrawal'].with_user(self.user_milker).create({
                'animal_id': cow.id, 'end_date': '2030-01-01', 'reason': 'x'})
        self.env['dairy.milk.withdrawal'].with_user(self.user_vet).create({
            'animal_id': cow.id, 'end_date': '2030-01-01', 'reason': 'x'})

    def test_multi_company_isolation(self):
        other = self.env['res.company'].create({'name': 'Other Farm'})
        foreign = self.env['dairy.animal'].create({'tag_number': 'OTHER-1', 'company_id': other.id})
        self.assertFalse(self.env['dairy.animal'].with_user(self.user_manager).search([('id', '=', foreign.id)]))
        # tag uniqueness is per company
        self.env['dairy.animal'].create({'tag_number': 'OTHER-1'})

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import HealthCommon


@tagged('post_install', '-at_install')
class TestHealthSecurity(HealthCommon):

    def test_non_vets_cannot_record_clinical_data(self):
        for user in (self.user_milker, self.user_feeder, self.user_sales, self.user_accountant):
            with self.assertRaises(AccessError):
                self._new_case(user=user)
            with self.assertRaises(AccessError):
                self.env['dairy.vaccination'].with_user(user).create(
                    {'animal_id': self.cow.id, 'product_id': self.vaccine.id})

    def test_dairy_users_can_read_health_history(self):
        case = self._new_case()
        self.assertEqual(case.with_user(self.user_milker).read(['name'])[0]['name'], case.name)
        with self.assertRaises(AccessError):
            case.with_user(self.user_milker).write({'severity': 'low'})

    def test_manager_and_vet_rights(self):
        self.assertTrue(self.user_vet.has_group('stock.group_stock_user'))
        case = self._new_case(user=self.user_manager)
        case.with_user(self.user_manager).write({'severity': 'high'})

    def test_multi_company_isolation(self):
        other = self.env['res.company'].create({'name': 'T Other Farm'})
        case = self._new_case()
        self.user_vet.write({'company_ids': [(4, other.id)], 'company_id': other.id})
        visible = self.env['dairy.health.case'].with_user(self.user_vet).with_context(
            allowed_company_ids=[other.id]).search([('id', '=', case.id)])
        self.assertFalse(visible)

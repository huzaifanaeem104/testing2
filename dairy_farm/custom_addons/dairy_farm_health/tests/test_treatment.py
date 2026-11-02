from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import HealthCommon


@tagged('post_install', '-at_install')
class TestTreatment(HealthCommon):

    def _diagnosed_case(self, animal=None):
        case = self._new_case(animal=animal, diagnosis='Clinical mastitis')
        case.action_diagnose()
        return case

    def _treatment(self, case, **vals):
        return self.env['dairy.treatment'].with_user(self.user_vet).create({
            'case_id': case.id, 'product_id': self.antibiotic.id, 'quantity': 3, 'duration_days': 3,
            'start_date': date.today(), **vals})

    def test_administer_issues_stock_posts_expense_and_restricts_milk(self):
        self._receive(self.antibiotic, 10)
        expense_before = self._account_balance(self.acc_vet_expense)
        case = self._diagnosed_case()
        treatment = self._treatment(case)
        self.assertEqual(treatment.route, 'im')
        self.assertEqual(treatment.milk_withdrawal_days, 4)
        self.assertEqual(treatment.end_date, date.today() + timedelta(days=2))
        self.assertEqual(treatment.withdrawal_end_date, date.today() + timedelta(days=6))

        treatment.with_user(self.user_vet).action_administer()
        self.assertEqual(treatment.state, 'administered')
        self.assertEqual(case.state, 'treatment')
        self.assertEqual(treatment.move_id.state, 'done')
        self.assertEqual(treatment.move_id.location_dest_id, self.consumption)
        self.assertAlmostEqual(treatment.cost_amount, 600.0)
        self.assertAlmostEqual(case.medicine_cost, 600.0)
        self.assertAlmostEqual(self.antibiotic.with_context(location=self.store.id).qty_available, 7)
        self.assertAlmostEqual(self._account_balance(self.acc_vet_expense) - expense_before, 600.0)

        withdrawal = treatment.withdrawal_id
        self.assertEqual(withdrawal.state, 'active')
        self.assertEqual(withdrawal.end_date, treatment.withdrawal_end_date)
        self.assertTrue(self.cow.has_active_withdrawal)
        # a treated cow is still milked; her milk is withheld from sale for the whole period
        self.assertTrue(self.cow.is_milking_eligible)
        Withdrawal = self.env['dairy.milk.withdrawal']
        self.assertEqual(Withdrawal._restricted_animals(self.cows, treatment.withdrawal_end_date), self.cow)
        self.assertFalse(Withdrawal._restricted_animals(self.cows, date.today() - timedelta(days=1)))

        # second click must not issue stock twice
        with self.assertRaises(UserError):
            treatment.action_administer()
        self.assertEqual(self.env['stock.move'].search_count([('origin', '=', treatment.name)]), 1)
        with self.assertRaises(UserError):
            treatment.quantity = 5  # locked once administered

        # closing the case does not lift the milk restriction
        case.outcome = 'recovered'
        case.action_close()
        self.assertEqual(withdrawal.state, 'active')
        self.assertTrue(self.cow.has_active_withdrawal)

    def test_insufficient_stock_blocks_issue(self):
        self._receive(self.antibiotic, 1)
        treatment = self._treatment(self._diagnosed_case())
        with self.assertRaises(UserError):
            treatment.action_administer()
        self.assertEqual(treatment.state, 'draft')
        self.assertFalse(treatment.withdrawal_id)

    def test_reverse_returns_stock_cancels_restriction_and_expense(self):
        self._receive(self.antibiotic, 10)
        expense_before = self._account_balance(self.acc_vet_expense)
        treatment = self._treatment(self._diagnosed_case())
        treatment.action_administer()
        with self.assertRaises(AccessError):
            treatment.with_user(self.user_milker).action_reverse()
        with self.assertRaises(UserError):
            treatment.with_user(self.user_vet).action_reverse()  # reason required
        treatment.reversal_reason = 'Recorded on the wrong cow'
        treatment.with_user(self.user_vet).action_reverse()
        self.assertEqual(treatment.state, 'reversed')
        self.assertEqual(treatment.reversal_move_id.state, 'done')
        self.assertEqual(treatment.reversal_move_id.origin_returned_move_id, treatment.move_id)
        self.assertAlmostEqual(self.antibiotic.with_context(location=self.store.id).qty_available, 10)
        self.assertAlmostEqual(self._account_balance(self.acc_vet_expense), expense_before)
        self.assertEqual(treatment.withdrawal_id.state, 'cancelled')
        self.assertFalse(self.cow.has_active_withdrawal)

    def test_non_stock_treatment_without_withdrawal(self):
        case = self._diagnosed_case()
        treatment = self.env['dairy.treatment'].create({'case_id': case.id, 'description': 'Udder massage, stripping'})
        treatment.action_administer()
        self.assertEqual(treatment.state, 'administered')
        self.assertFalse(treatment.move_id)
        self.assertFalse(treatment.withdrawal_id)

    def test_expired_lot_and_missing_lot_blocked(self):
        lot = self.env['stock.lot'].create({'name': 'T-EXP-1', 'product_id': self.vaccine.id,
                                            'expiration_date': date.today() - timedelta(days=1)})
        self._receive(self.vaccine, 5, lot)
        treatment = self._treatment(self._diagnosed_case(), product_id=self.vaccine.id, quantity=1)
        with self.assertRaises(UserError):
            treatment.action_administer()  # lot not selected
        treatment.lot_id = lot
        with self.assertRaises(UserError):
            treatment.action_administer()  # lot expired
        self.assertFalse(treatment.move_id)

    def test_zero_quantity_and_foreign_lot_blocked(self):
        self._receive(self.antibiotic, 10)
        treatment = self._treatment(self._diagnosed_case(), quantity=0)
        with self.assertRaises(UserError):
            treatment.action_administer()
        foreign_lot = self.env['stock.lot'].create({'name': 'T-OTHER', 'product_id': self.vaccine.id})
        treatment.write({'quantity': 1, 'lot_id': foreign_lot.id})
        with self.assertRaises(UserError):
            treatment.action_administer()
        self.assertFalse(treatment.withdrawal_id)

    def test_valuation_guard_requires_expense_account(self):
        self.consumption.write({'valuation_in_account_id': False, 'valuation_out_account_id': False})
        self._receive(self.antibiotic, 10)
        treatment = self._treatment(self._diagnosed_case())
        with self.assertRaises(UserError):
            treatment.action_administer()
        self.assertEqual(treatment.state, 'draft')

    def test_withdrawal_release_by_vet_only(self):
        self._receive(self.antibiotic, 10)
        treatment = self._treatment(self._diagnosed_case())
        treatment.action_administer()
        withdrawal = treatment.withdrawal_id
        with self.assertRaises(UserError):
            withdrawal.with_user(self.user_milker)._do_release(withdrawal.end_date, 'ok')
        withdrawal.with_user(self.user_vet)._do_release(withdrawal.end_date, 'Negative antibiotic residue test', 'RT-1')
        self.assertEqual(withdrawal.state, 'released')
        Withdrawal = self.env['dairy.milk.withdrawal']
        self.assertEqual(Withdrawal._restricted_animals(self.cow, withdrawal.start_date), self.cow,
                         'milk recorded before the release date stays withheld')
        self.assertFalse(Withdrawal._restricted_animals(self.cow, withdrawal.end_date))

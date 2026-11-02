from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import HealthCommon


@tagged('post_install', '-at_install')
class TestVaccination(HealthCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lot = cls.env['stock.lot'].create({'name': 'T-FMD-1', 'product_id': cls.vaccine.id,
                                               'expiration_date': date.today() + timedelta(days=200)})
        cls._receive(cls.vaccine, 20, cls.lot)

    def test_plan_wizard_idempotent(self):
        Wizard = self.env['dairy.vaccination.plan.wizard'].with_user(self.user_vet)
        vals = {'product_id': self.vaccine.id, 'planned_date': date.today(), 'dose_qty': 1, 'disease': 'FMD',
                'group_ids': [(6, 0, self.group_lactating.ids)]}
        Wizard.create(vals).action_plan()
        Wizard.create(vals).action_plan()
        vaccinations = self.env['dairy.vaccination'].search([('product_id', '=', self.vaccine.id)])
        self.assertEqual(len(vaccinations), 3)
        self.assertEqual(vaccinations.animal_id, self.cows)

    def test_done_issues_stock_and_schedules_next_dose(self):
        vac = self.env['dairy.vaccination'].with_user(self.user_vet).create({
            'animal_id': self.cow.id, 'product_id': self.vaccine.id, 'dose_qty': 2, 'lot_id': self.lot.id})
        vac.with_user(self.user_vet).action_done()
        self.assertEqual(vac.state, 'done')
        self.assertEqual(vac.move_id.state, 'done')
        self.assertEqual(vac.move_id.move_line_ids.lot_id, self.lot)
        self.assertAlmostEqual(vac.cost_amount, 100.0)
        self.assertAlmostEqual(self.vaccine.with_context(location=self.store.id).qty_available, 18)
        self.assertFalse(vac.withdrawal_id, 'vaccine without withdrawal period creates no restriction')
        nxt = vac.next_vaccination_id
        self.assertEqual(nxt.state, 'planned')
        self.assertEqual(nxt.planned_date, date.today() + timedelta(days=180))
        self.assertFalse(nxt.lot_id)
        with self.assertRaises(UserError):
            vac.action_done()
        self.assertEqual(self.env['dairy.vaccination'].search_count([('animal_id', '=', self.cow.id)]), 2)
        with self.assertRaises(UserError):
            vac.unlink()

    def test_vaccine_with_withdrawal_restricts_milk(self):
        self.vaccine.dairy_milk_withdrawal_days = 3
        vac = self.env['dairy.vaccination'].create({
            'animal_id': self.cow.id, 'product_id': self.vaccine.id, 'dose_qty': 1, 'lot_id': self.lot.id})
        vac.action_done()
        self.assertEqual(vac.withdrawal_id.end_date, date.today() + timedelta(days=3))
        self.assertTrue(self.cow.has_active_withdrawal)

    def test_reminder_cron_idempotent(self):
        vac = self.env['dairy.vaccination'].create({
            'animal_id': self.cow.id, 'product_id': self.vaccine.id, 'dose_qty': 1,
            'planned_date': date.today() - timedelta(days=1)})
        self.assertTrue(vac.is_overdue)
        self.assertIn(vac, self.env['dairy.vaccination'].search([('is_overdue', '=', True)]))
        Vac = self.env['dairy.vaccination']
        Vac._cron_vaccination_reminders()
        Vac._cron_vaccination_reminders()
        self.assertEqual(len(vac.activity_ids.filtered(lambda a: a.summary == vac._due_summary())), 1)
        vac.lot_id = self.lot
        vac.action_done()
        self.assertFalse(vac.activity_ids.filtered(lambda a: a.summary == vac._due_summary()))

    def test_cancel_clears_reminder(self):
        vac = self.env['dairy.vaccination'].create({
            'animal_id': self.cow.id, 'product_id': self.vaccine.id, 'planned_date': date.today()})
        self.env['dairy.vaccination']._cron_vaccination_reminders()
        self.assertTrue(vac.activity_ids)
        vac.action_cancel()
        self.assertFalse(vac.activity_ids)

    def test_done_requires_dose_and_active_animal(self):
        vac = self.env['dairy.vaccination'].create({
            'animal_id': self.cow.id, 'product_id': self.vaccine.id, 'lot_id': self.lot.id})
        with self.assertRaises(UserError):
            vac.action_done()  # no dose quantity: stock would silently not be issued
        vac.dose_qty = 1
        self.cow.write({'active_status': 'deceased', 'exit_date': date.today(), 'exit_reason': 'Test'})
        with self.assertRaises(UserError):
            vac.action_done()
        self.assertEqual(vac.state, 'planned')
        self.assertAlmostEqual(self.vaccine.with_context(location=self.store.id).qty_available, 20)

    def test_medicine_product_defaults_category(self):
        defaults = self.env['product.template'].with_context(default_is_dairy_medicine=True).default_get(['categ_id'])
        self.assertEqual(defaults['categ_id'], self.env.ref('dairy_farm_health.product_category_dairy_medicine').id)

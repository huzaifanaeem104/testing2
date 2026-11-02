from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged

from .common import StockAccountingCommon


@tagged('post_install', '-at_install', 'dairy')
class TestFeed(StockAccountingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company._dairy_feed_setup_locations()
        cls.consumption_location = cls.company.dairy_feed_consumption_location_id
        cls.wastage_location = cls.company.dairy_feed_wastage_location_id
        cls._set_location_account(cls.consumption_location, cls.acc_feed_expense)
        cls._set_location_account(cls.wastage_location, cls.acc_wastage_expense)
        cls.feed_category = cls._real_time_category('T Dairy Feed RT')
        cls.wanda = cls.env['product.product'].create({
            'name': 'T Wanda (Concentrate)', 'is_storable': True, 'is_dairy_feed': True,
            'uom_id': cls.uom_kg.id, 'uom_po_id': cls.uom_kg.id, 'categ_id': cls.feed_category.id,
            'standard_price': 0.0})
        cls.cows = cls._create_cows(5)

    def _consume(self, qty, user=None, **kw):
        vals = {'product_id': self.wanda.id, 'actual_qty': qty, 'allocation_type': 'group',
                'group_id': self.group_lactating.id}
        vals.update(kw)
        Consumption = self.env['dairy.feed.consumption'].with_user(user or self.user_feeder)
        return Consumption.create(vals)

    def test_purchase_partial_receipt_bill_payment(self):
        po = self._purchase_and_receive(self.wanda, 1000, 50.0, receive_qty=600)
        self.assertEqual(self.wanda.qty_available, 600)
        self.assertEqual(len(po.picking_ids), 2, 'Backorder for the remaining 400 kg')
        backorder = po.picking_ids.filtered(lambda p: p.state != 'done')
        backorder.move_ids.quantity = 400
        backorder.move_ids.picked = True
        backorder.button_validate()
        self.assertEqual(self.wanda.qty_available, 1000)
        self.assertAlmostEqual(self._account_balance(self.acc_stock_valuation), 50000)
        # vendor bill through standard Purchase -> Accounting
        po.action_create_invoice()
        bill = po.invoice_ids
        bill.invoice_date = fields.Date.today()
        bill.action_post()
        self.assertEqual(bill.state, 'posted')
        self.assertAlmostEqual(self._account_balance(self.acc_stock_in), 0, msg='Interim received account cleared by bill')
        payable = bill.line_ids.filtered(lambda l: l.account_type == 'liability_payable')
        self.assertAlmostEqual(-sum(payable.mapped('balance')), bill.amount_total)
        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bill.ids).create({})._create_payments()
        self.assertTrue(payment)
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        # a second invoice action does not duplicate the bill
        self.assertEqual(po.invoice_status, 'invoiced')

    def test_consumption_posts_stock_and_accounting(self):
        self._purchase_and_receive(self.wanda, 1000, 50.0)
        rec = self._consume(200)
        self.assertEqual(rec.location_dest_id, self.consumption_location)
        rec.action_validate()
        self.assertEqual(rec.state, 'done')
        self.assertEqual(rec.move_id.state, 'done')
        self.assertEqual(self.wanda.qty_available, 800)
        self.assertAlmostEqual(rec.cost_amount, 10000)
        self.assertEqual(rec.head_count, 5)
        self.assertAlmostEqual(rec.cost_per_head, 2000)
        # perpetual valuation: Dr feed expense / Cr inventory, recognised once
        self.assertAlmostEqual(self._account_balance(self.acc_feed_expense), 10000)
        self.assertAlmostEqual(self._account_balance(self.acc_stock_valuation), 40000)
        # double posting is impossible
        with self.assertRaises(UserError):
            rec.action_validate()
        self.assertEqual(self.env['stock.move'].search_count([('origin', '=', rec.name)]), 1)
        with self.assertRaises(UserError):
            rec.write({'actual_qty': 150})
        with self.assertRaises(UserError):
            rec.unlink()
        # per-cow allocation report
        report = self.env['dairy.feed.allocation.report'].search([('consumption_id', '=', rec.id)])
        self.assertEqual(len(report), 5)
        self.assertAlmostEqual(sum(report.mapped('cost')), 10000)
        self.assertAlmostEqual(self.cows[0].feed_cost_30d, 2000)

    def test_valuation_guard_and_periodic(self):
        self._purchase_and_receive(self.wanda, 100, 50.0)
        self.company.anglo_saxon_accounting = False
        rec = self._consume(10)
        with self.assertRaises(UserError):
            rec.action_validate()
        self.company.anglo_saxon_accounting = True
        self.consumption_location.valuation_out_account_id = False
        with self.assertRaises(UserError):
            rec.action_validate()
        self._set_location_account(self.consumption_location, self.acc_feed_expense)
        # periodic valuation: the bill is the expense, consumption posts no journal entry
        periodic = self.env['product.product'].create({
            'name': 'T Wheat Straw', 'is_storable': True, 'is_dairy_feed': True, 'uom_id': self.uom_kg.id,
            'uom_po_id': self.uom_kg.id, 'categ_id': self.env.ref('dairy_farm_feed.product_category_dairy_feed').id})
        self.assertEqual(periodic.valuation, 'manual_periodic')
        self._purchase_and_receive(periodic, 500, 10.0)
        straw = self._consume(100, product_id=periodic.id)
        straw.action_validate()
        self.assertAlmostEqual(straw.cost_amount, 1000)
        self.assertFalse(straw.move_id.sudo().account_move_ids)
        self.assertAlmostEqual(self._account_balance(self.acc_feed_expense), 0)

    def test_insufficient_stock(self):
        self._purchase_and_receive(self.wanda, 100, 50.0)
        rec = self._consume(150)
        with self.assertRaises(UserError):
            rec.action_validate()
        self.assertEqual(rec.state, 'draft')
        self.assertEqual(self.wanda.qty_available, 100)

    def test_reversal_and_wastage(self):
        self._purchase_and_receive(self.wanda, 500, 40.0)
        rec = self._consume(100)
        rec.action_validate()
        with self.assertRaises(UserError):
            rec.with_user(self.user_manager).action_reverse()  # no reason
        rec.with_user(self.user_manager).write({'correction_reason': 'Recorded twice by mistake'})
        rec.with_user(self.user_manager).action_reverse()
        self.assertEqual(rec.state, 'reversed')
        self.assertEqual(self.wanda.qty_available, 500)
        self.assertAlmostEqual(self._account_balance(self.acc_feed_expense), 0)
        with self.assertRaises(UserError):
            rec.with_user(self.user_manager).action_reverse()
        waste = self._consume(25, consumption_type='wastage', allocation_type='group')
        self.assertEqual(waste.location_dest_id, self.wastage_location)
        waste.action_validate()
        self.assertEqual(self.wanda.qty_available, 475)
        self.assertAlmostEqual(self._account_balance(self.acc_wastage_expense), 1000)
        self.assertFalse(self.env['dairy.feed.allocation.report'].search([('consumption_id', '=', waste.id)]))

    def test_supplier_return(self):
        po = self._purchase_and_receive(self.wanda, 300, 50.0)
        picking = po.picking_ids
        wizard = Form(self.env['stock.return.picking'].with_context(active_ids=picking.ids, active_id=picking.id,
                                                                    active_model='stock.picking')).save()
        wizard.product_return_moves.quantity = 50
        res = wizard.action_create_returns()
        ret = self.env['stock.picking'].browse(res['res_id'])
        ret.move_ids.quantity = 50
        ret.move_ids.picked = True
        ret.button_validate()
        self.assertEqual(self.wanda.qty_available, 250)
        self.assertEqual(po.order_line.qty_received, 250)

    def test_plan_generation_idempotent(self):
        plan = self.env['dairy.feed.plan'].create({
            'target_type': 'group', 'group_id': self.group_lactating.id,
            'line_ids': [(0, 0, {'product_id': self.wanda.id, 'qty_per_head': 4.0, 'shift_id': self.shift_morning.id})],
        })
        self.assertEqual(plan.line_ids.planned_qty, 20.0)
        with self.assertRaises(UserError):
            plan._generate_consumption(fields.Date.today())
        plan.with_user(self.user_manager).action_activate()
        first = plan._generate_consumption(fields.Date.today())
        second = plan._generate_consumption(fields.Date.today())
        self.assertEqual(len(first), 1)
        self.assertFalse(second)
        self.assertEqual(first.planned_qty, 20.0)

    def test_feed_security(self):
        self._purchase_and_receive(self.wanda, 100, 50.0)
        with self.assertRaises(AccessError):
            self._consume(10, user=self.user_milker)
        with self.assertRaises(AccessError):
            self.env['dairy.feed.plan'].with_user(self.user_feeder).create({
                'target_type': 'group', 'group_id': self.group_lactating.id})
        rec = self._consume(10)
        with self.assertRaises(AccessError):
            rec.with_user(self.user_accountant).action_validate()
        # feed operators post stock operations but have no accounting rights
        self.assertFalse(self.user_feeder.has_group('account.group_account_invoice'))
        rec.action_validate()

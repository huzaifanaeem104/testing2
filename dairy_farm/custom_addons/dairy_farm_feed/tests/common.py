from odoo.tests import Form

from odoo.addons.dairy_farm_core.tests.common import DairyCommon


class StockAccountingCommon(DairyCommon):
    """Real-time (perpetual) valuation setup used by feed, health and sales tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.acc_stock_valuation = Account.create({'name': 'T Feed & Medicine Inventory', 'code': '119901', 'account_type': 'asset_current'})
        cls.acc_stock_in = Account.create({'name': 'T Stock Interim Received', 'code': '119902', 'account_type': 'asset_current', 'reconcile': True})
        cls.acc_stock_out = Account.create({'name': 'T Stock Interim Delivered', 'code': '119903', 'account_type': 'asset_current', 'reconcile': True})
        cls.acc_feed_expense = Account.create({'name': 'T Feed Consumption Expense', 'code': '419901', 'account_type': 'expense'})
        cls.acc_wastage_expense = Account.create({'name': 'T Feed Wastage Expense', 'code': '419902', 'account_type': 'expense'})
        cls.stock_journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.vendor = cls.env['res.partner'].create({'name': 'T Feed Supplier'})
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        # perpetual valuation requires Anglo-Saxon accounting (bills hit the interim account)
        cls.company.anglo_saxon_accounting = True

    @classmethod
    def _set_location_account(cls, location, account):
        location.write({'valuation_in_account_id': account.id, 'valuation_out_account_id': account.id})

    @classmethod
    def _real_time_category(cls, name):
        return cls.env['product.category'].create({
            'name': name,
            'property_cost_method': 'average',
            'property_valuation': 'real_time',
            'property_stock_valuation_account_id': cls.acc_stock_valuation.id,
            'property_stock_account_input_categ_id': cls.acc_stock_in.id,
            'property_stock_account_output_categ_id': cls.acc_stock_out.id,
            'property_stock_journal': cls.stock_journal.id,
        })

    @classmethod
    def _purchase_and_receive(cls, product, qty, price, receive_qty=None, backorder=True):
        po = cls.env['purchase.order'].create({
            'partner_id': cls.vendor.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_qty': qty, 'price_unit': price})],
        })
        po.button_confirm()
        picking = po.picking_ids
        picking.move_ids.quantity = receive_qty if receive_qty is not None else qty
        picking.move_ids.picked = True
        res = picking.button_validate()
        if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
            wizard = Form.from_action(cls.env, res).save()
            wizard.process() if backorder else wizard.process_cancel_backorder()
        return po

    @classmethod
    def _account_balance(cls, account):
        lines = cls.env['account.move.line'].search([('account_id', '=', account.id), ('parent_state', '=', 'posted')])
        return sum(lines.mapped('balance'))

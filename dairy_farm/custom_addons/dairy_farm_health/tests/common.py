from odoo.addons.dairy_farm_core.tests.common import DairyCommon


class HealthCommon(DairyCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.acc_stock_valuation = Account.create({'name': 'T Medicine Inventory', 'code': '119911', 'account_type': 'asset_current'})
        cls.acc_stock_in = Account.create({'name': 'T Med Interim Received', 'code': '119912', 'account_type': 'asset_current', 'reconcile': True})
        cls.acc_stock_out = Account.create({'name': 'T Med Interim Delivered', 'code': '119913', 'account_type': 'asset_current', 'reconcile': True})
        cls.acc_vet_expense = Account.create({'name': 'T Veterinary Expense', 'code': '419911', 'account_type': 'expense'})
        cls.stock_journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        cls.company.anglo_saxon_accounting = True
        cls.company._dairy_health_setup_locations()
        cls.store, cls.consumption = cls.company._dairy_medicine_locations()
        cls.consumption.write({'valuation_in_account_id': cls.acc_vet_expense.id,
                               'valuation_out_account_id': cls.acc_vet_expense.id})
        cls.category = cls.env['product.category'].create({
            'name': 'T Medicine RT',
            'property_cost_method': 'average',
            'property_valuation': 'real_time',
            'property_stock_valuation_account_id': cls.acc_stock_valuation.id,
            'property_stock_account_input_categ_id': cls.acc_stock_in.id,
            'property_stock_account_output_categ_id': cls.acc_stock_out.id,
            'property_stock_journal': cls.stock_journal.id,
        })
        cls.antibiotic = cls.env['product.product'].create({
            'name': 'T Oxytetracycline', 'is_storable': True, 'type': 'consu', 'categ_id': cls.category.id,
            'is_dairy_medicine': True, 'dairy_milk_withdrawal_days': 4, 'dairy_default_route': 'im',
            'standard_price': 200.0,
        })
        cls.vaccine = cls.env['product.product'].create({
            'name': 'T FMD Vaccine', 'is_storable': True, 'type': 'consu', 'categ_id': cls.category.id,
            'is_dairy_medicine': True, 'is_dairy_vaccine': True, 'dairy_revaccination_days': 180,
            'tracking': 'lot', 'use_expiration_date': True, 'standard_price': 50.0,
        })
        cls.cows = cls._create_cows(3, prefix='T-HC')
        cls.cow = cls.cows[0]

    @classmethod
    def _receive(cls, product, qty, lot=None):
        cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id, 'location_id': cls.store.id, 'inventory_quantity': qty,
            'lot_id': lot.id if lot else False,
        }).action_apply_inventory()

    @classmethod
    def _account_balance(cls, account):
        lines = cls.env['account.move.line'].search([('account_id', '=', account.id), ('parent_state', '=', 'posted')])
        return sum(lines.mapped('balance'))

    def _new_case(self, animal=None, user=None, **vals):
        Case = self.env['dairy.health.case'].with_user(user or self.user_vet)
        return Case.create({'animal_id': (animal or self.cow).id, 'symptoms': 'Swollen quarter, clots',
                            'condition': 'mastitis', **vals})

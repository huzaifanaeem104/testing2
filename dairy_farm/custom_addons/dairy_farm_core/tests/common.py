from odoo.tests.common import TransactionCase, new_test_user


class DairyCommon(TransactionCase):
    """Shared fixtures for all dairy addons: one user per role and a herd."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.company
        cls.user_admin_dairy = new_test_user(cls.env, 'dairy_admin', groups='base.group_user,dairy_farm_core.group_dairy_admin')
        cls.user_manager = new_test_user(cls.env, 'dairy_manager', groups='base.group_user,dairy_farm_core.group_dairy_manager')
        cls.user_milker = new_test_user(cls.env, 'dairy_milker', groups='base.group_user,dairy_farm_core.group_dairy_milking_operator')
        cls.user_feeder = new_test_user(cls.env, 'dairy_feeder', groups='base.group_user,dairy_farm_core.group_dairy_feed_operator')
        cls.user_vet = new_test_user(cls.env, 'dairy_vet', groups='base.group_user,dairy_farm_core.group_dairy_veterinarian')
        cls.user_sales = new_test_user(cls.env, 'dairy_sales', groups='base.group_user,dairy_farm_core.group_dairy_sales_operator')
        cls.user_accountant = new_test_user(cls.env, 'dairy_accountant', groups='base.group_user,dairy_farm_core.group_dairy_accountant')

        cls.breed = cls.env['dairy.breed'].create({'name': 'Test Sahiwal', 'expected_daily_yield': 12})
        cls.barn = cls.env['dairy.location'].create({'name': 'Test Barn A', 'location_type': 'barn', 'capacity': 60})
        cls.group_lactating = cls.env['dairy.animal.group'].create({
            'name': 'Test Lactating', 'group_type': 'lactating', 'location_id': cls.barn.id})
        cls.shift_morning = cls.env.ref('dairy_farm_core.shift_morning')
        cls.shift_afternoon = cls.env.ref('dairy_farm_core.shift_afternoon')
        cls.shift_evening = cls.env.ref('dairy_farm_core.shift_evening')
        cls.bull = cls.env['dairy.animal'].create({
            'tag_number': 'T-BULL-1', 'animal_type': 'bull', 'gender': 'male',
            'breed_id': cls.breed.id, 'birth_date': '2018-01-01'})

    @classmethod
    def _create_cows(cls, count, prefix='T-COW', lactating=True):
        return cls.env['dairy.animal'].create([{
            'tag_number': f'{prefix}-{i:03d}',
            'animal_type': 'cow',
            'gender': 'female',
            'breed_id': cls.breed.id,
            'birth_date': '2020-03-01',
            'location_id': cls.barn.id,
            'group_id': cls.group_lactating.id,
            'production_status': 'lactating' if lactating else 'dry',
            'lactation_number': 1,
        } for i in range(1, count + 1)])

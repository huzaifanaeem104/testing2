{
    'name': 'Dairy Farm - Core',
    'version': '18.0.1.0.0',
    'category': 'Agriculture/Dairy Farm',
    'summary': 'Animal registry, breeds, locations, groups, shifts, '
               'milk-withdrawal restrictions and shared dairy security',
    'description': """
Dairy Farm Core
===============
Foundation of the Dairy Farm ERP:

* Animal registry with sequence references and unique tags
* Breeds, farm locations (barns, pens, ...) and animal groups
* Configurable milking/feeding shifts
* Milk-withdrawal restrictions shared by health, milking and sales
* Shared security groups, record rules and farm settings
""",
    'author': 'Dairy Farm ERP',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'contacts'],
    'data': [
        'security/dairy_security.xml',
        'security/ir.model.access.csv',
        'security/dairy_rules.xml',
        'data/ir_sequence_data.xml',
        'data/dairy_shift_data.xml',
        'data/ir_cron_data.xml',
        'views/dairy_animal_views.xml',
        'views/dairy_breed_views.xml',
        'views/dairy_location_views.xml',
        'views/dairy_animal_group_views.xml',
        'views/dairy_shift_views.xml',
        'views/dairy_milk_withdrawal_views.xml',
        'views/res_config_settings_views.xml',
        'views/dairy_menus.xml',
    ],
    'application': True,
    'installable': True,
}

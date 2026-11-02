{
    'name': 'AGES Contracts Menu',
    'summary': 'Contract menus on Project module',
    'version': '18.0.1.0.3',
    'category': 'Project',
    'author': 'Muhammad Sana Ullah',
    'depends': ['project'],
    # Contract business logic is in ages_contracts (install that module too).
    'data': [
        'security/ir.model.access.csv',
        'views/ages_contract_views.xml',
        'views/ages_running_bill_views.xml',
        'views/ages_mobilization_advance_views.xml',
        'views/ages_retention_recovery_views.xml',
        'views/ages_contract_menus.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

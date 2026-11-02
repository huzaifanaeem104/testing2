{
    'name': 'Custom Access Rights - Journal Entry',
    'summary': 'Draft / Validate / Post approval workflow for Journal Entries',
    'version': '18.0.1.0.1',
    'category': 'Accounting/Accounting',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': ['account', 'bus'],
    'data': [
        'views/res_users_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

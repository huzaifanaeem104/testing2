# -*- coding: utf-8 -*-
{
    'name': 'AGES Account Asset Customizations',
    'version': '18.0.1.1.0',
    'category': 'Accounting/Accounting',
    'summary': 'AGES enhancements for account asset categories and invoice line integration',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'om_account_asset',
    ],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

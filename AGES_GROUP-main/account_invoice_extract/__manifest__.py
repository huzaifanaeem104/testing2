# -*- coding: utf-8 -*-
{
    'name': 'Invoice Digitization',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Fill vendor bills and customer invoices from scanned documents',
    'depends': ['account_extract'],
    'data': [
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': True,
}

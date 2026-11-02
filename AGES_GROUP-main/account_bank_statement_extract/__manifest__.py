# -*- coding: utf-8 -*-
{
    'name': 'Bank Statement Digitization',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Digitize scanned bank statements into statement lines',
    'depends': ['account_extract', 'account_bank_statement_import'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': True,
}

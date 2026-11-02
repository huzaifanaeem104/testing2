# -*- coding: utf-8 -*-
{
    'name': 'AGES Reports',
    'summary': 'Landscape print reports for expenses, payments, journal entries, RFQs, POs and receipts',
    'version': '18.0.1.4.2',
    'category': 'Accounting/Accounting',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'purchase',
        'stock',
        'ages_expense',
        'ages_account_dimensions',
        'ages_custom_reports',
        'ages_project',
        'ages_company',
    ],
    'data': [
        'report/paperformat.xml',
        'report/report_actions.xml',
        'report/templates.xml',
        'views/print_buttons.xml',
    ],
    'installable': True,
    'application': False,
}

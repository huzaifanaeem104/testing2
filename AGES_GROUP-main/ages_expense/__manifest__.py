# -*- coding: utf-8 -*-
{
    'name': 'Expense',
    'version': '18.0.1.8.8',
    'category': 'Accounting/Expenses',
    'summary': 'Manage Vendor Expenses, Payment Journal Entries, and Analytic Tagging.',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'project',
        'hr',
        'ages_company',
        'ages_project',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ages_expense_security.xml',
        'data/ir_sequence_data.xml',
        'views/ages_expense_views.xml',
        'views/ages_expense_menu_views.xml',
        'views/account_payment_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': True,
    'post_init_hook': 'post_init_hook',
    'assets': {
        'web.assets_backend': [
            'ages_expense/static/src/expense_line_duplicate/expense_line_duplicate.js',
        ],
    },
}

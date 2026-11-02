# -*- coding: utf-8 -*-
{
    'name': 'AGES Partner Ledger WHT Split',
    'summary': 'Split Partner Ledger payment rows into actual amount and withholding tax',
    'description': """
On Partner Ledger, a customer/vendor payment with withholding tax currently
shows one line for the gross (net + tax). This module keeps the partner total
the same and shows two lines instead:

* the actual amount (without tax)
* the withholding tax amount
    """,
    'version': '18.0.1.1.0',
    'category': 'Accounting/Accounting',
    'author': 'Muhammad Sana Ullah',
    'depends': [
        'ages_custom_reports',
        'l10n_account_withholding_tax',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

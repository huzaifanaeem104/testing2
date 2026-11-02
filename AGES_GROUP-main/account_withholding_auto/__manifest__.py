{
    'name': 'Account Withholding Auto',
    'version': '18.0.1.0.1',
    'category': 'Accounting',
    'summary': 'Auto-populate withholding line counter, account and base amount',
    'description': """
        This module extends account.withholding.line to:
        - Automatically assign counter numbers (1, 2, 3...) to withholding lines
        - Auto-populate account_id from tax_id
        - Auto-populate base_amount from account.payment.register (Pay dialog) or account.payment (standalone payment)
        - Automatically renumbers lines when lines are added or removed
        - On standalone account.payment: same behaviour as Pay dialog (auto-pick amount in lines,
          auto-add account when tax is selected, net total calculated by base withholding module)
    """,
    'author': 'Sanaullah',
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'depends': ['l10n_account_withholding_tax'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}


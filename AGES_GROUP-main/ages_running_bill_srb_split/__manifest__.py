# -*- coding: utf-8 -*-
{
    'name': 'AGES Running Bill SRB 20/80',
    'summary': 'Running-bill SRB: credit 100% sales tax, debit WTH share (net 80%)',
    'description': """
Optional companion for ages_running_bills SRB 20/80 handling.

Invoice lines (from ages_running_bills):

* Sales Tax → SRB credit 100%
* WTH on Sales Tax → SRB debit (e.g. 20%) on the same account → net 80%
* Mobilization / Retention recovery lines restored
    """,
    'version': '18.0.1.0.4',
    'category': 'Accounting/Accounting',
    'author': 'Muhammad Sana Ullah',
    'depends': [
        'ages_running_bills',
        'ages_account_dimensions',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_apply_srb_split',
    'uninstall_hook': 'uninstall_revert_srb_split',
}

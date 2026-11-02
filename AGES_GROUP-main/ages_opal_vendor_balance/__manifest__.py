# -*- coding: utf-8 -*-
{
    'name': 'AGES OPAL Vendor Balance by Project',
    'summary': 'Static OPAL vendor-by-project reference next to live Odoo payables',
    'description': """
Reference report under Accounting → AGES Reporting → Partner Reports.

Imports the cleaned OPAL Vendor Balance workbook as static rows. Odoo
overall payable is read from posted payable journal items only — this
module never posts, reconciles, or writes ledgers.
    """,
    'version': '18.0.1.0.16',
    'category': 'Accounting/Accounting',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'web',
        'project',
        'report_xlsx',
        'ages_custom_reports',
        'ages_company',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/opal_map_views.xml',
        'views/opal_import_views.xml',
        'wizard/opal_import_wizard_views.xml',
        'report/opal_report_template.xml',
        'views/opal_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ages_opal_vendor_balance/static/src/opal_vendor_balance_report/opal_vendor_balance_report.scss',
            'ages_opal_vendor_balance/static/src/opal_vendor_balance_report/opal_vendor_balance_report.js',
            'ages_opal_vendor_balance/static/src/opal_vendor_balance_report/opal_vendor_balance_report.xml',
            'ages_opal_vendor_balance/static/src/ledger_opal/ledger_opal.scss',
            'ages_opal_vendor_balance/static/src/ledger_opal/ledger_opal.js',
            'ages_opal_vendor_balance/static/src/ledger_opal/ledger_opal.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

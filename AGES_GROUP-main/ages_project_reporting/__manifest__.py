# -*- coding: utf-8 -*-
{
    'name': 'AGES Project Reporting',
    'summary': 'Project reports: mobilization and retention cash movement (debit / credit / account)',
    'description': """
AGES Project Reporting
======================

Interactive web reports under Accounting → AGES Reporting → Project Reports.

Both reports fold Client → Contract, then show posted journal items:
Date, Account, Debit, Credit, Balance. Click a line to open the journal entry.

Mobilization: cash-in payments plus mobilization-account recoveries on running bills.
Retention: retention-account withholdings on running bills plus release payments.
    """,
    'author': 'Muhammad Sana Ullah',
    'category': 'Project',
    'version': '18.0.1.1.12',
    'depends': [
        'account',
        'project',
        'report_xlsx',
        'web',
        'ages_custom_reports',
        'ages_company',
        'ages_contracts',
        'ages_running_bills',
        'ages_retention_recovery',
        'ages_mobilization_received',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/retention_report_template.xml',
        'report/mobilization_report_template.xml',
        'views/ages_reporting_menus.xml',
        'views/retention_report_wizard_view.xml',
        'views/mobilization_report_wizard_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ages_project_reporting/static/src/retention_report/retention_report.scss',
            'ages_project_reporting/static/src/retention_report/retention_report.js',
            'ages_project_reporting/static/src/retention_report/retention_report.xml',
            'ages_project_reporting/static/src/mobilization_report/mobilization_report.scss',
            'ages_project_reporting/static/src/mobilization_report/mobilization_report.js',
            'ages_project_reporting/static/src/mobilization_report/mobilization_report.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}

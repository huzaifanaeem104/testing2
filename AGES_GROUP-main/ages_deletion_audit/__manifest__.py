# -*- coding: utf-8 -*-
{
    'name': 'AGES Deletion Audit',
    'summary': 'Centralized audit trail for deleted business records',
    'description': """
When a meaningful business record is deleted, keep an independent log of
who deleted it, which model and module it belonged to, when it happened,
how it was deleted, and a useful pre-deletion snapshot.

Audited areas: Project, Sales, Purchase, Accounting, Expense,
Purchase Request, Inventory, Employees, Payroll, Attendances.

New business models in those addons are included automatically. Administrators
can include or exclude specific models without changing code.
    """,
    'version': '18.0.1.0.1',
    'category': 'Extra Tools',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'project',
        'sale',
        'purchase',
        'account',
        'stock',
        'hr',
        'hr_attendance',
        'purchase_request',
        'ages_expense',
        'ages_hr_work_entry_bridge',
    ],
    'data': [
        'security/ages_deletion_audit_security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'views/ages_deletion_audit_views.xml',
        'views/ages_deletion_audit_exception_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

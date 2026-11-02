# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Work Entry Bridge',
    'version': '18.0.1.0.2',
    'category': 'Human Resources/Payroll',
    'summary': 'Payroll menus and work-entry UX without Enterprise Gantt',
    'description': """
Replaces Enterprise hr_work_entry_contract_enterprise + hr_gantt dependency
with community calendar/list work entry access under the Payroll application.
    """,
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'hr_work_entry_contract',
    ],
    'data': [
        'views/hr_payroll_menu.xml',
        'views/hr_work_entry_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

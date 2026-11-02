# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Work Entry Attendance',
    'version': '18.0.1.0.4',
    'category': 'Human Resources/Employees',
    'summary': 'Generate work entries from employee attendances',
    'description': """
AGES reimplementation of attendance-based work entry generation.

Adds the Attendances work-entry source on contracts and builds work
entries from hr.attendance check-in / check-out periods.
    """,
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'hr_work_entry_contract',
        'hr_attendance',
    ],
    'data': [
        'views/hr_contract_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

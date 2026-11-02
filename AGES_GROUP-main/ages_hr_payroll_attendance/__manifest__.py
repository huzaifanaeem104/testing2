# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Payroll Attendance',
    'version': '18.0.1.0.1',
    'category': 'Human Resources/Payroll',
    'summary': 'Extra hours from attendance on hourly payslips',
    'description': """
AGES bridge between attendance work entries and payroll.

Splits approved overtime out of regular attendance hours for hourly
contracts and links payslips to matching attendance records.
    """,
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'ages_hr_work_entry_attendance',
        'ages_hr_payroll',
    ],
    'data': [
        'data/hr_payroll_attendance_data.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

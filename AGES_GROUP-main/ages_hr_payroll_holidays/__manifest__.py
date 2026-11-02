# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Payroll Holidays',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Defer time off that overlaps validated payslips',
    'description': """
AGES reimplementation of payroll / time-off deferral.

When a leave is validated over a closed payslip period, payroll processing
is deferred and a payroll officer activity is scheduled instead of rewriting
already paid work entries.
    """,
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'hr_work_entry_holidays',
        'ages_hr_payroll',
        'hr_holidays',
    ],
    'data': [
        'security/hr_payroll_holidays_security.xml',
        'data/mail_activity_data.xml',
        'data/ir_actions_server_data.xml',
        'views/res_config_settings_views.xml',
        'views/hr_leave_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Payroll Accounting',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Create accounting journal entries from payslips',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': ['ages_hr_payroll', 'account'],
    'data': [
        'views/hr_salary_rule_views.xml',
        'views/hr_payroll_structure_views.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}

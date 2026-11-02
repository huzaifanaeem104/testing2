# -*- coding: utf-8 -*-
{
    'name': 'Expenses in Payslips',
    'version': '18.0.1.1.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Reimburse approved employee expenses on payslips',
    'depends': ['hr_expense', 'ages_hr_payroll'],
    'data': [
        'data/hr_payroll_expense_data.xml',
        'views/hr_expense_views.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'installable': True,
    'post_init_hook': '_add_expense_rule_to_structures',
}

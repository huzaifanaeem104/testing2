# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Loan & Advance',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Employee advance and loan applications with payroll deduction',
    'description': """
Advance and loan applications with approval workflow, accounting journal
entries on confirm, equal-principal loan installments, and flexible
auto-injection into payslip other inputs as deductions.
    """,
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'ages_hr_payroll',
        'ages_hr_payroll_account',
    ],
    'data': [
        'security/hr_loan_advance_security.xml',
        'security/ir.model.access.csv',
        'data/hr_loan_advance_data.xml',
        'data/ir_sequence_data.xml',
        'views/hr_advance_application_views.xml',
        'views/hr_loan_application_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_loan_advance_menu.xml',
    ],
    'assets': {},
    'installable': True,
    'application': False,
    'auto_install': False,
}

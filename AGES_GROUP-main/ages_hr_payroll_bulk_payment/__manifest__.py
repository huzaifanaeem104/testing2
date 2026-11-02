# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Payroll Bulk Payment & Analytic Integration',
    'version': '18.0.1.2.1',
    'category': 'Human Resources/Payroll',
    'summary': 'Project & Analytic tagging on payslips, auto-posted expense journal entries, smart button links, and bulk payment wizard.',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'project',
        'account',
        'ages_hr_payroll',
        'ages_hr_payroll_account',
        'ages_hr_employee_tracking',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_payslip_views.xml',
        'wizard/hr_payslip_bulk_payment_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}

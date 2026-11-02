# -*- coding: utf-8 -*-
{
    'name': 'AGES HR Employee Tracking & Transfer',
    'version': '18.0.1.1.0',
    'category': 'Human Resources/Employee',
    'summary': 'Track employee project transfers, job position updates, wage history, and contract reference auto-generation.',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'project',
        'hr_contract',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/hr_employee_transfer_wizard_views.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
}

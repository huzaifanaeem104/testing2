# -*- coding: utf-8 -*-
{
    'name': 'AGES Purchase Request Dimensions',
    'summary': 'Project and Analytic on purchase requests, copied to POs and vendor bills',
    'version': '18.0.1.1.1',
    'category': 'Purchase Management',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'purchase_request',
        'ages_project',
        'ages_account_dimensions',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_request_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

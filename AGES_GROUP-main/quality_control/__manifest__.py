# -*- coding: utf-8 -*-
{
    'name': 'Quality',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing/Quality',
    'summary': 'Add quality checks to transfer operations',
    'depends': ['quality'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
        'views/quality_menus.xml',
        'wizard/quality_check_wizard_views.xml',
    ],
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}

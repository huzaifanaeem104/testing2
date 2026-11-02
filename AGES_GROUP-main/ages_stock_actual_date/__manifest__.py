# -*- coding: utf-8 -*-
{
    'name': 'AGES Stock Actual Date Customization',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Make actual_date field mandatory on stock moves and pickings',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_move_actual_date',
    ],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

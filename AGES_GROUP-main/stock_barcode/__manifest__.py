# -*- coding: utf-8 -*-
{
    'name': 'Barcode',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Process inventory operations with a barcode scanner',
    'depends': ['stock', 'barcodes'],
    'data': [
        'security/stock_barcode_security.xml',
        'security/ir.model.access.csv',
        'views/stock_barcode_views.xml',
        'views/stock_picking_views.xml',
        'views/res_config_settings_views.xml',
        'report/stock_barcode_reports.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_barcode/static/src/stock_barcode.scss',
            'stock_barcode/static/src/stock_barcode.js',
            'stock_barcode/static/src/stock_barcode.xml',
        ],
    },
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}

# -*- coding: utf-8 -*-
{
    'name': 'Universal Column Resize',
    'summary': 'Drag to resize columns on every Odoo list view and custom report tables (persisted)',
    'description': """
Universal Column Resize
=======================

Standalone module that enables drag-to-resize columns across the whole backend:

* All standard list / tree views (Sales, Purchase, Accounting, Inventory, HR, ...)
* Embedded one2many / many2many lists (Sale Order Lines, Purchase Order Lines, Invoice Lines, ...)
* AGES Reporting interactive tables (General Ledger, Partner Ledger, Balance Sheet, ...)
* Other custom ``table`` reports rendered in the backend

Features
--------
* Drag the right edge of any column header to resize
* Widths are remembered per view / table in the browser (localStorage)
* Optional-columns menu includes **Reset column widths** when a saved size exists
* Zero configuration — install and it applies everywhere
* Depends only on ``web``
    """,
    'version': '18.0.1.0.4',
    'category': 'Productivity',
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'web_universal_column_resize/static/src/list/width_store.js',
            'web_universal_column_resize/static/src/list/persistent_column_width_hook.js',
            'web_universal_column_resize/static/src/list/list_renderer_patch.js',
            'web_universal_column_resize/static/src/list/list_renderer_patch.xml',
            'web_universal_column_resize/static/src/generic/generic_table_resize.js',
            'web_universal_column_resize/static/src/column_resize.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

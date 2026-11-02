# -*- coding: utf-8 -*-
{
    'name': 'AGES Purchaser',
    'summary': 'Purchaser (employee) on Purchase Orders and Vendor Bills',
    'description': """
Adds a Purchaser field (Many2one to Employees) on:
- Purchase Order form
- Vendor Bill / Refund / Receipt form

When a vendor bill is created from a purchase order, the purchaser is copied across.
    """,
    'version': '18.0.1.0.1',
    'category': 'Purchases',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'purchase',
        'account',
        'hr',
    ],
    'data': [
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

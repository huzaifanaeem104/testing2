{
    'name': 'Custom Client & Vendor Working',
    'summary': 'Client/Vendor flags on Contacts, restricted selection on Sales/Purchase, and Customer renamed to Client on Sales',
    'version': '18.0.1.0.1',
    'category': 'Sales',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': ['base', 'sale', 'purchase'],
    'data': [
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/sale_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

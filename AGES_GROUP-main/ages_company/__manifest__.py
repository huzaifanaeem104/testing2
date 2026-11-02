{
    'name': 'AGES Sub Companies',
    'summary': 'Sub Companies configuration with account remapping on journal items',
    'version': '18.0.1.1.0',
    'category': 'Accounting/Accounting',
    'author': 'Muhammad Sana Ullah',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/ages_sub_company_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

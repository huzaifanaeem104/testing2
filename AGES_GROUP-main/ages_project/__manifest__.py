{
    'name': 'AGES Project',
    'summary': 'Project creation wizard, auto location/analytic, and contract linking',
    'version': '18.0.1.0.5',
    'category': 'Project',
    'author': 'Muhammad Sana Ullah',
    'depends': [
        'sale_project',
        'ages_contracts',
        'ages_company',
        'ages_project_configs',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_project_views.xml',
        'views/ages_contract_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

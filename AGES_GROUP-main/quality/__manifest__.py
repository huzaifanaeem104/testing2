# -*- coding: utf-8 -*-
{
    'name': 'Quality Base',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing/Quality',
    'summary': 'Quality points, checks and alerts for transfers',
    'depends': ['stock'],
    'data': [
        'security/quality_security.xml',
        'security/ir.model.access.csv',
        'data/quality_data.xml',
        'views/quality_views.xml',
    ],
    'author': 'AGES Group',
    'license': 'LGPL-3',
    'installable': True,
}

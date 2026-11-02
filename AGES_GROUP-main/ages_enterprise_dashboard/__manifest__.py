# -*- coding: utf-8 -*-
{
    'name': 'AGES Enterprise Management Dashboard',
    'summary': 'Centralized module-wise management intelligence for AGES GROUP',
    'version': '18.0.2.2.6',
    'category': 'Productivity',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'account',
        'analytic',
        'project',
        'purchase',
        'stock',
        'sale',
        'hr',
        'hr_attendance',
        'ages_company',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/dashboard_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ages_enterprise_dashboard/static/src/dashboard/dashboard.scss',
            'ages_enterprise_dashboard/static/src/dashboard/widgets/*.js',
            'ages_enterprise_dashboard/static/src/dashboard/dashboard.xml',
            'ages_enterprise_dashboard/static/src/dashboard/dashboard.js',
        ],
        'web.assets_web_dark': [
            'ages_enterprise_dashboard/static/src/dashboard/dashboard.dark.scss',
        ],
        'web.assets_unit_tests': [
            'ages_enterprise_dashboard/static/tests/**/*.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}

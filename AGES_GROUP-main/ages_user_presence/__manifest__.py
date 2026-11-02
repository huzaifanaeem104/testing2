# -*- coding: utf-8 -*-
{
    'name': 'AGES User Presence',
    'summary': 'Real-time distinction between logged-in sessions and active Odoo use',
    'description': """
Track who is authenticated in Odoo and whether they are actually using it.

Presence is independent from the HTTP session:

- Active / Using Odoo — tab visible, focused, recent interaction
- Background — still logged in, Odoo tab not visible or not focused
- Idle — Odoo visible, no recent interaction
- Inactive — session still valid, no recent browser heartbeat
- Logged out — session ended

Multiple browsers and devices are tracked as separate sessions.
Administrators can watch a live list and force-logout a session.
    """,
    'version': '18.0.1.0.1',
    'category': 'Extra Tools',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'bus'],
    'data': [
        'security/ages_user_presence_security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'data/ir_cron_data.xml',
        'views/ages_user_session_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ages_user_presence/static/src/presence.scss',
            'ages_user_presence/static/src/presence_service.js',
            'ages_user_presence/static/src/presence_list.xml',
            'ages_user_presence/static/src/presence_list_view.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

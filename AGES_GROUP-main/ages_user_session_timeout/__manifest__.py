# -*- coding: utf-8 -*-
{
    'name': 'AGES User Session Timeout',
    'summary': 'Per-user inactivity logout, per-browser sessions, and a warning before expiry',
    'description': """
Automatically log a user out after they stop interacting with Odoo.

User policy Disabled: no inactivity logout.
User policy Custom: that user's timeout and warning.
User policy Use default: Settings default, if the user is in scope.

Timeout is per browser session. The browser shows the warning; the server
invalidates the HTTP session.
    """,
    'version': '18.0.2.0.1',
    'category': 'Extra Tools',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'ages_user_presence'],
    'data': [
        'security/ages_session_timeout_security.xml',
        'data/ir_config_parameter_data.xml',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
        'views/ages_user_session_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ages_user_session_timeout/static/src/session_timeout.scss',
            'ages_user_session_timeout/static/src/session_timeout_dialog.js',
            'ages_user_session_timeout/static/src/session_timeout_dialog.xml',
            'ages_user_session_timeout/static/src/session_timeout_service.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

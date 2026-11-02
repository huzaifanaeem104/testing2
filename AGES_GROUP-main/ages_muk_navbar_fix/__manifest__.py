{
    'name': 'AGES MuK Navbar Fix',
    'summary': 'Hide app menus on the home screen when using MuK theme',
    'version': '18.0.1.0.6',
    'category': 'Tools/UI',
    'author': 'Muhammad Sana Ullah',
    'depends': [
        'web',
        'muk_web_theme',
    ],
    'assets': {
        'web.assets_backend': [
            (
                'after',
                'muk_web_theme/static/src/webclient/navbar/navbar.js',
                'ages_muk_navbar_fix/static/src/webclient/navbar/navbar.js',
            ),
            (
                'after',
                'muk_web_theme/static/src/webclient/appsmenu/appsmenu.js',
                'ages_muk_navbar_fix/static/src/webclient/navbar/appsmenu_patch.js',
            ),
            (
                'after',
                'muk_web_theme/static/src/webclient/navbar/navbar.xml',
                'ages_muk_navbar_fix/static/src/webclient/navbar/navbar.xml',
            ),
            'ages_muk_navbar_fix/static/src/webclient/navbar/appsmenu.scss',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

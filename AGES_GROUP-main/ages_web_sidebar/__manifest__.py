{
    'name': 'AGES Web Sidebar',
    'summary': 'Auto-collapse MuK AppsBar to icons with smooth hover expand',
    'version': '18.0.1.0.1',
    'category': 'Tools/UI',
    'author': 'Muhammad Sana Ullah',
    'license': 'LGPL-3',
    'depends': [
        'muk_web_appsbar',
        'muk_web_theme',
    ],
    'assets': {
        'web.assets_backend': [
            (
                'after',
                'muk_web_appsbar/static/src/webclient/appsbar/appsbar.js',
                'ages_web_sidebar/static/src/webclient/appsbar/appsbar.js',
            ),
            (
                'after',
                'muk_web_appsbar/static/src/webclient/appsbar/appsbar.xml',
                'ages_web_sidebar/static/src/webclient/appsbar/appsbar.xml',
            ),
            (
                'after',
                'muk_web_appsbar/static/src/webclient/appsbar/appsbar.scss',
                'ages_web_sidebar/static/src/webclient/appsbar/appsbar.scss',
            ),
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

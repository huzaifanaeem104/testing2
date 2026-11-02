{
    'name': 'AGES Chatter Resize',
    'summary': 'Resize, hide and restore the form chatter; the main form stays responsive',
    'version': '18.0.1.0.1',
    'category': 'Productivity/Discuss',
    'author': 'Muhammad Sana Ullah',
    'depends': [
        'web',
        'mail',
    ],
    'images': ['static/description/icon.png'],
    'assets': {
        'web.assets_backend': [
            'ages_chatter_resize/static/src/chatter_resize_service.js',
            'ages_chatter_resize/static/src/form_controller_patch.js',
            'ages_chatter_resize/static/src/chatter_patch.js',
            'ages_chatter_resize/static/src/form_controller.xml',
            'ages_chatter_resize/static/src/chatter.xml',
            'ages_chatter_resize/static/src/chatter_resize.scss',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

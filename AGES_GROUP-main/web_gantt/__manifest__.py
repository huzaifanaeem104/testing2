# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Web Gantt',
    'category': 'Hidden',
    'description': """
Odoo Web Gantt chart view.
=============================

Community port of the Odoo 18 Enterprise Gantt view (`web_gantt`).
    """,
    'version': '2.0',
    'depends': ['web'],
    'assets': {
        'web._assets_primary_variables': [
            'web_gantt/static/src/gantt_view.variables.scss',
        ],
        'web.assets_backend_lazy': [
            'web_gantt/static/src/**/*',
            # Don't include dark mode files in light mode
            ('remove', 'web_gantt/static/src/**/*.dark.scss'),
        ],
        # Community (web_hierarchy) pattern: inject dark variables without web_enterprise
        'web.assets_backend_lazy_dark': [
            (
                'before',
                'web_gantt/static/src/gantt_view.variables.scss',
                'web_gantt/static/src/gantt_view.variables.dark.scss',
            ),
            'web_gantt/static/src/gantt_view.dark.scss',
        ],
    },
    'auto_install': True,
    'license': 'LGPL-3',
}

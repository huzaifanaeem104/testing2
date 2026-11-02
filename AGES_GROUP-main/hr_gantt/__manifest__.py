# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Employees in Gantt',
    'category': 'Hidden',
    'summary': 'Employees in Gantt',
    'version': '1.0',
    'description': """
Community port of the Odoo 18 Enterprise employee Gantt renderer (`hr_gantt`).
    """,
    'depends': ['hr', 'web_gantt'],
    'auto_install': True,
    'license': 'LGPL-3',
    'assets': {
        'web.assets_backend_lazy': [
            'hr_gantt/static/src/**/*',
        ],
    }
}

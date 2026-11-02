# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': "Attendance Gantt",
    'summary': """Gantt view for Attendance""",
    'description': """
Gantt view for Attendance.

Community port of the Odoo 18 Enterprise Attendances Overview Gantt
(`hr_attendance_gantt`): employees on rows, hours 0–23 on the day scale.
    """,
    'category': 'Human Resources/Attendances',
    'version': '1.0',
    'depends': ['hr_attendance', 'hr_gantt'],
    'auto_install': True,
    'data': [
        'views/hr_attendance_gantt.xml'
    ],
    'assets': {
        'web.assets_backend_lazy': [
            'hr_attendance_gantt/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}

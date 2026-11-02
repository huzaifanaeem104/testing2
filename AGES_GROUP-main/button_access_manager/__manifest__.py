# -*- coding: utf-8 -*-
{
    'name': 'Button Access Manager',
    'version': '18.0.4.0.0',
    'category': 'Tools',
    'summary': 'Access Profiles, hide/block buttons, and hide home apps and menus per user, group, or profile.',
    'description': """
Button Access Manager hides and blocks New, Import, Export, Delete,
Duplicate, Archive, Print, and scanned object/action buttons per user
or group.

It also hides home apps, menus, and submenus (denylist) per user, group,
or Access Profile. Tiles disappear because menus are removed from
load_menus. Opening a fully hidden menu action by URL is blocked.
Hiding an app does not revoke Access Rights groups.

Access Profiles generate a hidden res.groups plus ir.model.access and
optional ir.rule, then reuse the existing button engine for Confirm,
Print, Archive, and custom buttons.

Fields, tabs, chatter, and search filters remain out of scope (Ninja).
If both products hide the same menu, the menu is hidden (union).

The true database superuser (uid=1) cannot be restricted, by Odoo design.
Regular Administrator logins are fully covered. Community edition only.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'base_import'],
    'data': [
        'security/access_profile_security.xml',
        'security/ir.model.access.csv',
        'views/button_access_rule_views.xml',
        'views/menu_access_views.xml',
        'views/button_scan_wizard_views.xml',
        'views/button_copy_wizard_views.xml',
        'views/access_profile_views.xml',
        'views/res_users_views.xml',
        'views/res_groups_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'button_access_manager/static/src/js/button_access_service.js',
            'button_access_manager/static/src/js/button_hider.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}

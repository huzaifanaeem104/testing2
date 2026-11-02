{
    "name": "NARC Direct Print",
    "summary": "Send selected PDF reports straight to the printer — others still download",
    "description": """
NARC Direct Print
=================

Reports download as PDF by default. Open a report and set Default
behavior to Print when that report should go to the workstation printer.

* Download PDF remains the default
* Only opted-in reports print directly
* No on-screen preview for those reports
* First print on a new PC offers Windows or Linux QZ Tray setup
    """,
    "version": "18.0.2.5.3",
    "category": "Productivity",
    "author": "Synavos",
    "website": "https://synavos.com/",
    "support": "info@synavos.com",
    "images": [
        "static/description/screenshot_settings.png",
        "static/description/screenshot_print.png",
    ],
    "depends": ["base", "web", "base_setup"],
    "data": [
        "data/ir_config_parameter.xml",
        "views/ir_actions_report_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "narc_direct_print/static/src/js/report_action_direct_print.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
    "price": 0,
    "currency": "USD",
}

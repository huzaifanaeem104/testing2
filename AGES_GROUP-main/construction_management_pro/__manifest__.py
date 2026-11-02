{
    "name": "Construction Management Pro",
    "version": "18.0.1.0.1",
    "summary": "Integrated construction projects, BOQ, materials, procurement, MRP, site progress and contracts",
    "description": """
Construction Management Pro for Odoo 18
=======================================
A construction execution layer tightly integrated with Project, Manufacturing,
Inventory and Purchase. It provides construction project controls, BOQs,
material requests, manufacturing packages, daily logs, progress measurement,
change orders, subcontract tracking, RFIs and equipment assignments.
    """,
    "author": "Custom Development",
    "website": "https://www.odoo.com",
    "category": "Services/Project",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "project",
        "product",
        "uom",
        "stock",
        "purchase",
        "mrp",
    ],
    "data": [
        "security/construction_security.xml",
        "security/ir.model.access.csv",
        "data/construction_sequence.xml",
        "views/construction_project_views.xml",
        "views/construction_boq_views.xml",
        "views/construction_material_request_views.xml",
        "views/construction_site_views.xml",
        "views/construction_change_order_views.xml",
        "views/construction_contract_views.xml",
        "views/construction_integration_views.xml",
        "views/construction_menus.xml",
        "report/construction_boq_report.xml",
    ],
    "application": True,
    "installable": True,
    "auto_install": False,
}

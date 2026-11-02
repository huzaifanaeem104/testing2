# -*- coding: utf-8 -*-
{
    "name": "AGES Civil Material",
    "summary": "Civil Material POs: daily CM slips (L×B×H), GRN + gate pass, one month-end bill",
    "description": """
Civil Material procurement (standalone)
=======================================

* Checkbox **Civil Material PO** on purchase orders (separate from normal POs).
* Daily **Civil Material Slips**: supplier, first measurement slip, time, truck#,
  lines with L / B / H → quantity (CFT), remarks.
* Slip creates partial GRN + gate pass (reuses AGES gate pass flow).
* Standard Create Bill blocked on civil POs; use **Create monthly bill** instead.
* Month-end bill auto-fills one line per slip (date, truck, slip no, qty, rate, amount);
  draft lines remain editable before posting.
    """,
    "version": "18.0.1.5.1",
    "category": "Purchases",
    "author": "Muhammad Sana Ullah",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "purchase_stock",
        "stock",
        "account",
        "ages_gate_pass_extended",
        "ages_purchase_request",
        "ages_custom_reports",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/purchase_order_views.xml",
        "views/ages_civil_material_slip_views.xml",
        "wizard/ages_civil_monthly_bill_wizard_views.xml",
        "wizard/ages_civil_material_report_wizard_views.xml",
        "report/ages_civil_material_report.xml",
        "report/ages_civil_material_templates.xml",
        "views/ages_civil_material_menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}

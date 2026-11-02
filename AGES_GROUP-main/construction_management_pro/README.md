# Construction Management Pro — Odoo 18

An installable Odoo 18 add-on for construction companies, designed to integrate construction execution with Odoo Project, Manufacturing (MRP), Inventory, and Purchase.

## Core workflow

1. Create a **Construction Project** with client, contract, site store and source warehouse location.
2. Build and approve a **BOQ** with material, labor, equipment, subcontract and manufactured/fabricated lines.
3. Generate **Project Tasks** from BOQ work lines.
4. Generate **Manufacturing Orders** from fabricated BOQ lines using existing Odoo BOMs.
5. Raise **Material Requests** from the project/task.
6. Convert a material request either to an **RFQ** or an **Internal Site Transfer**.
7. Record **Daily Site Logs** and **Progress Measurements**.
8. Track **RFIs**, **Change Orders**, **Subcontracts**, and **Equipment Assignments**.
9. Use project KPIs to monitor BOQ budget, approved changes, purchase commitments and progress.

## Integrations

- `project.project` — construction project master and KPI layer
- `project.task` — quantity-based construction task progress
- `mrp.production` — linked fabrication/manufacturing orders
- `purchase.order` — linked project procurement
- `stock.picking` — linked material/site transfers
- `mrp.bom` — manufacturing BOM used for fabricated BOQ lines

## Install

Copy `construction_management_pro` into your custom addons path, update the Apps list, then install **Construction Management Pro**.

Required Odoo apps are installed automatically through dependencies: Project, Inventory, Purchase, Manufacturing, Product/UoM, and Discuss/Mail.

## Recommended roles

- Construction User
- Site Engineer
- Construction Procurement
- Construction Manager

## Notes

This module is an original implementation based on construction-management workflows and public product descriptions. It does not contain or reproduce proprietary source code from third-party Odoo apps.


## 18.0.1.0.1 compatibility fix
- Restricted inherited Purchase, Stock Picking, and MRP form XPaths to fields belonging to the parent document model.
- Prevents Construction fields from being injected into embedded one2many subviews such as `stock.move` inside the Manufacturing Order form.
- Fixes installation error: `Field construction_project_id does not exist in model stock.move`.

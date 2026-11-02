# Deployment / UAT Checklist

1. Install or enable Odoo **Project**, **Inventory**, **Purchase**, and **Manufacturing**.
2. Add this folder to the server `addons_path`, restart Odoo, and update the Apps list.
3. Install **Construction Management Pro**.
4. Give users the appropriate native Odoo access rights (Project / Inventory / Purchase / Manufacturing) plus one of the Construction roles.
5. Create a construction project and set its default source stock location and site stock location.
6. Test BOQ approval, task generation, one fabricated BOQ line with an existing BOM, one material RFQ, and one internal site transfer.
7. Validate daily logs, progress measurement, change-order approval, RFI, subcontract, and equipment assignment flows.

## Validation performed in this package

- Python files compile successfully.
- XML files parse successfully.
- Manifest-listed files exist.
- Odoo 18 core field names used for MRP, Stock and Purchase were cross-checked against the Odoo 18 source tree.

A full installation test still requires an actual Odoo 18 Enterprise runtime and database, which is not available in the packaging environment used to generate this add-on.


## 18.0.1.0.1 compatibility fix
- Restricted inherited Purchase, Stock Picking, and MRP form XPaths to fields belonging to the parent document model.
- Prevents Construction fields from being injected into embedded one2many subviews such as `stock.move` inside the Manufacturing Order form.
- Fixes installation error: `Field construction_project_id does not exist in model stock.move`.

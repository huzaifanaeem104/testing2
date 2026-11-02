from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    construction_project_id = fields.Many2one("project.project", domain="[('is_construction', '=', True)]", index=True, tracking=True)
    construction_material_request_id = fields.Many2one("construction.material.request", index=True, copy=False)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    construction_project_id = fields.Many2one("project.project", domain="[('is_construction', '=', True)]", index=True)
    construction_material_request_id = fields.Many2one("construction.material.request", index=True, copy=False)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    construction_project_id = fields.Many2one("project.project", domain="[('is_construction', '=', True)]", index=True)
    construction_boq_id = fields.Many2one("construction.boq", index=True, copy=False)
    construction_boq_line_id = fields.Many2one("construction.boq.line", index=True, copy=False)

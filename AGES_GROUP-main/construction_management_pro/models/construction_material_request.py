from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionMaterialRequest(models.Model):
    _name = "construction.material.request"
    _description = "Construction Material Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    task_id = fields.Many2one("project.task", domain="[('project_id', '=', project_id)]")
    requested_by = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    request_date = fields.Date(default=fields.Date.context_today, required=True)
    required_date = fields.Date()
    source_location_id = fields.Many2one("stock.location", domain="[('usage', '=', 'internal')]")
    destination_location_id = fields.Many2one("stock.location", domain="[('usage', '=', 'internal')]")
    vendor_id = fields.Many2one("res.partner", domain="[('supplier_rank', '>', 0)]")
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("ordered", "RFQ Created"),
            ("issued", "Issued"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("construction.material.request.line", "request_id", copy=True)
    purchase_order_id = fields.Many2one("purchase.order", readonly=True, copy=False)
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.material.request") or "New"
        records = super().create(vals_list)
        for rec in records:
            if not rec.source_location_id and rec.project_id.source_location_id:
                rec.source_location_id = rec.project_id.source_location_id
            if not rec.destination_location_id and rec.project_id.site_location_id:
                rec.destination_location_id = rec.project_id.site_location_id
        return records

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if self.project_id:
            self.source_location_id = self.project_id.source_location_id
            self.destination_location_id = self.project_id.site_location_id

    def action_submit(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_("Add at least one material line."))
            record.state = "submitted"

    def action_approve(self):
        self.write({"state": "approved"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_create_rfq(self):
        self.ensure_one()
        if self.purchase_order_id:
            return self._open_purchase_order()
        if self.state not in ("approved", "submitted"):
            raise UserError(_("Approve the request before creating an RFQ."))
        if not self.vendor_id:
            raise UserError(_("Select a vendor before creating an RFQ."))
        order = self.env["purchase.order"].create({
            "partner_id": self.vendor_id.id,
            "origin": self.name,
            "construction_project_id": self.project_id.id,
            "construction_material_request_id": self.id,
        })
        for line in self.line_ids:
            if not line.product_id.purchase_ok:
                raise UserError(_("Product %s is not enabled for purchasing.") % line.product_id.display_name)
            self.env["purchase.order.line"].create({
                "order_id": order.id,
                "product_id": line.product_id.id,
                "name": line.description or line.product_id.display_name,
                "product_qty": line.quantity,
                "product_uom": line.uom_id.id,
                "price_unit": line.estimated_unit_cost,
                "date_planned": fields.Datetime.now(),
            })
        self.write({"purchase_order_id": order.id, "state": "ordered"})
        return self._open_purchase_order()

    def _open_purchase_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Request for Quotation",
            "res_model": "purchase.order",
            "view_mode": "form",
            "res_id": self.purchase_order_id.id,
        }

    def action_create_internal_transfer(self):
        self.ensure_one()
        if self.picking_id:
            return self._open_picking()
        if self.state not in ("approved", "ordered"):
            raise UserError(_("Approve the request before issuing materials."))
        if not self.source_location_id or not self.destination_location_id:
            raise UserError(_("Both source and destination locations are required."))
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
        ], limit=1)
        if not picking_type:
            raise UserError(_("No internal transfer operation type was found."))
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": self.source_location_id.id,
            "location_dest_id": self.destination_location_id.id,
            "origin": self.name,
            "construction_project_id": self.project_id.id,
            "construction_material_request_id": self.id,
        })
        for line in self.line_ids:
            self.env["stock.move"].create({
                "name": line.description or line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.uom_id.id,
                "location_id": self.source_location_id.id,
                "location_dest_id": self.destination_location_id.id,
                "picking_id": picking.id,
            })
        picking.action_confirm()
        self.write({"picking_id": picking.id, "state": "issued"})
        return self._open_picking()

    def _open_picking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Internal Transfer",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
        }


class ConstructionMaterialRequestLine(models.Model):
    _name = "construction.material.request.line"
    _description = "Construction Material Request Line"

    request_id = fields.Many2one("construction.material.request", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="request_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True)
    description = fields.Char(required=True)
    quantity = fields.Float(default=1.0, required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM", required=True)
    estimated_unit_cost = fields.Float()
    boq_line_id = fields.Many2one("construction.boq.line", string="BOQ Line")

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            self.estimated_unit_cost = self.product_id.standard_price

    @api.constrains("quantity")
    def _check_quantity(self):
        if any(line.quantity <= 0 for line in self):
            raise ValidationError(_("Requested quantity must be greater than zero."))

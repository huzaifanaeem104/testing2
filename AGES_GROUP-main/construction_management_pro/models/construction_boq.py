from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionBoq(models.Model):
    _name = "construction.boq"
    _description = "Construction Bill of Quantities"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    partner_id = fields.Many2one(related="project_id.partner_id", store=True, readonly=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)
    revision = fields.Char(default="R0", tracking=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("construction.boq.line", "boq_id", copy=True)
    material_amount = fields.Monetary(compute="_compute_amounts", store=True)
    labor_amount = fields.Monetary(compute="_compute_amounts", store=True)
    equipment_amount = fields.Monetary(compute="_compute_amounts", store=True)
    subcontract_amount = fields.Monetary(compute="_compute_amounts", store=True)
    manufactured_amount = fields.Monetary(compute="_compute_amounts", store=True)
    total_amount = fields.Monetary(compute="_compute_amounts", store=True)
    notes = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.boq") or "New"
        return super().create(vals_list)

    @api.depends("line_ids.subtotal", "line_ids.line_type")
    def _compute_amounts(self):
        for boq in self:
            buckets = {key: 0.0 for key in ["material", "labor", "equipment", "subcontract", "manufactured"]}
            for line in boq.line_ids:
                buckets[line.line_type] = buckets.get(line.line_type, 0.0) + line.subtotal
            boq.material_amount = buckets["material"]
            boq.labor_amount = buckets["labor"]
            boq.equipment_amount = buckets["equipment"]
            boq.subcontract_amount = buckets["subcontract"]
            boq.manufactured_amount = buckets["manufactured"]
            boq.total_amount = sum(buckets.values())

    def action_submit(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_("Add at least one BOQ line before submission."))
            record.state = "submitted"

    def action_approve(self):
        self.write({"state": "approved"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_create_tasks(self):
        self.ensure_one()
        created = self.env["project.task"]
        for line in self.line_ids.filtered(lambda l: l.line_type != "material" and not l.task_id):
            task = self.env["project.task"].create({
                "name": line.description or line.product_id.display_name,
                "project_id": self.project_id.id,
                "is_construction_task": True,
                "boq_line_id": line.id,
                "planned_qty": line.quantity,
                "construction_uom_id": line.uom_id.id,
            })
            line.task_id = task.id
            created |= task
        if not created:
            raise UserError(_("No eligible BOQ lines were available for task creation."))
        return {
            "type": "ir.actions.act_window",
            "name": "Construction Tasks",
            "res_model": "project.task",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }

    def action_create_manufacturing_orders(self):
        self.ensure_one()
        productions = self.env["mrp.production"]
        lines = self.line_ids.filtered(lambda l: l.line_type == "manufactured" and not l.production_id)
        for line in lines:
            if not line.product_id:
                raise UserError(_("A product is required on manufactured BOQ lines."))
            bom = line.bom_id
            if not bom:
                bom = self.env["mrp.bom"].search([
                    ("type", "=", "normal"),
                    ("company_id", "in", [False, self.project_id.company_id.id]),
                    "|",
                    ("product_id", "=", line.product_id.id),
                    "&",
                    ("product_id", "=", False),
                    ("product_tmpl_id", "=", line.product_id.product_tmpl_id.id),
                ], limit=1)
            if not bom:
                raise UserError(_("No Bill of Materials was found for %s.") % line.product_id.display_name)
            production = self.env["mrp.production"].create({
                "product_id": line.product_id.id,
                "product_qty": line.quantity,
                "product_uom_id": line.uom_id.id,
                "bom_id": bom.id,
                "origin": "%s / %s" % (self.project_id.display_name, self.name),
                "construction_project_id": self.project_id.id,
                "construction_boq_id": self.id,
                "construction_boq_line_id": line.id,
            })
            production.action_confirm()
            line.production_id = production.id
            productions |= production
        if not productions:
            raise UserError(_("No new manufactured BOQ lines are available."))
        return {
            "type": "ir.actions.act_window",
            "name": "Manufacturing Orders",
            "res_model": "mrp.production",
            "view_mode": "list,form",
            "domain": [("id", "in", productions.ids)],
        }


class ConstructionBoqLine(models.Model):
    _name = "construction.boq.line"
    _description = "Construction BOQ Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    boq_id = fields.Many2one("construction.boq", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="boq_id.company_id", store=True)
    currency_id = fields.Many2one(related="boq_id.currency_id", store=True)
    project_id = fields.Many2one(related="boq_id.project_id", store=True)
    line_type = fields.Selection(
        [
            ("material", "Material"),
            ("labor", "Labor"),
            ("equipment", "Equipment"),
            ("subcontract", "Subcontract"),
            ("manufactured", "Manufactured/Fabricated"),
        ],
        default="material",
        required=True,
    )
    code = fields.Char()
    product_id = fields.Many2one("product.product")
    description = fields.Char(required=True)
    quantity = fields.Float(default=1.0, required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM", required=True)
    unit_cost = fields.Monetary(required=True)
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True)
    planned_start = fields.Date()
    planned_end = fields.Date()
    task_id = fields.Many2one("project.task", readonly=True, copy=False)
    bom_id = fields.Many2one("mrp.bom", string="Manufacturing BOM")
    production_id = fields.Many2one("mrp.production", readonly=True, copy=False)

    @api.depends("quantity", "unit_cost")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price

    @api.constrains("quantity", "unit_cost")
    def _check_positive_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("BOQ quantity must be greater than zero."))
            if line.unit_cost < 0:
                raise ValidationError(_("BOQ unit cost cannot be negative."))

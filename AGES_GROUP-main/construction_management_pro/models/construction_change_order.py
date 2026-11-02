from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionChangeOrder(models.Model):
    _name = "construction.change.order"
    _description = "Construction Change Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    reason = fields.Text(required=True)
    impact_days = fields.Integer(string="Schedule Impact (Days)")
    line_ids = fields.One2many("construction.change.order.line", "change_order_id", copy=True)
    amount_total = fields.Monetary(compute="_compute_amount", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    approved_date = fields.Date(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.change.order") or "New"
        return super().create(vals_list)

    @api.depends("line_ids.subtotal")
    def _compute_amount(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped("subtotal"))

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one change-order line."))
            rec.state = "submitted"

    def action_approve(self):
        self.write({"state": "approved", "approved_by": self.env.user.id, "approved_date": fields.Date.context_today(self)})

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_reset(self):
        self.write({"state": "draft"})


class ConstructionChangeOrderLine(models.Model):
    _name = "construction.change.order.line"
    _description = "Construction Change Order Line"

    change_order_id = fields.Many2one("construction.change.order", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="change_order_id.company_id", store=True)
    currency_id = fields.Many2one(related="change_order_id.currency_id", store=True)
    product_id = fields.Many2one("product.product")
    description = fields.Char(required=True)
    quantity = fields.Float(default=1.0)
    uom_id = fields.Many2one("uom.uom", string="UoM", required=True)
    unit_cost = fields.Monetary()
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True)

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

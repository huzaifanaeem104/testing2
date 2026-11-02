from odoo import api, fields, models


class ConstructionSubcontract(models.Model):
    _name = "construction.subcontract"
    _description = "Construction Subcontract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    partner_id = fields.Many2one("res.partner", string="Subcontractor", required=True, tracking=True)
    task_id = fields.Many2one("project.task", domain="[('project_id', '=', project_id)]")
    scope = fields.Html(required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    contract_amount = fields.Monetary(tracking=True)
    retention_percent = fields.Float(default=5.0)
    retention_amount = fields.Monetary(compute="_compute_retention", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("completed", "Completed"), ("terminated", "Terminated")],
        default="draft",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.subcontract") or "New"
        return super().create(vals_list)

    @api.depends("contract_amount", "retention_percent")
    def _compute_retention(self):
        for rec in self:
            rec.retention_amount = rec.contract_amount * rec.retention_percent / 100.0

    def action_activate(self):
        self.write({"state": "active"})

    def action_complete(self):
        self.write({"state": "completed"})

    def action_terminate(self):
        self.write({"state": "terminated"})


class ConstructionEquipmentAssignment(models.Model):
    _name = "construction.equipment.assignment"
    _description = "Construction Equipment Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    task_id = fields.Many2one("project.task", domain="[('project_id', '=', project_id)]")
    equipment_id = fields.Many2one("product.product", required=True, string="Equipment")
    operator_id = fields.Many2one("res.users")
    date_from = fields.Datetime(required=True)
    date_to = fields.Datetime()
    hourly_rate = fields.Monetary()
    planned_hours = fields.Float()
    actual_hours = fields.Float(tracking=True)
    total_cost = fields.Monetary(compute="_compute_total_cost", store=True)
    state = fields.Selection(
        [("planned", "Planned"), ("onsite", "On Site"), ("returned", "Returned"), ("cancel", "Cancelled")],
        default="planned",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.equipment.assignment") or "New"
        return super().create(vals_list)

    @api.depends("hourly_rate", "actual_hours")
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.hourly_rate * rec.actual_hours

    def action_onsite(self):
        self.write({"state": "onsite"})

    def action_return(self):
        self.write({"state": "returned"})

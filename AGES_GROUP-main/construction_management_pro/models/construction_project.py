from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    is_construction = fields.Boolean(string="Construction Project", default=False, tracking=True)
    construction_code = fields.Char(string="Construction Code", copy=False, tracking=True)
    contract_number = fields.Char(tracking=True)
    contract_value = fields.Monetary(currency_field="currency_id", tracking=True)
    construction_state = fields.Selection(
        [
            ("preconstruction", "Pre-Construction"),
            ("mobilization", "Mobilization"),
            ("execution", "Execution"),
            ("handover", "Handover"),
            ("closed", "Closed"),
        ],
        default="preconstruction",
        tracking=True,
    )
    site_address = fields.Text()
    site_location_id = fields.Many2one(
        "stock.location",
        string="Site Stock Location",
        domain="[('usage', '=', 'internal')]",
        help="Internal stock location representing the construction site store.",
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Default Source Location",
        domain="[('usage', '=', 'internal')]",
    )
    approved_boq_amount = fields.Monetary(compute="_compute_construction_kpis", currency_field="currency_id")
    variation_amount = fields.Monetary(compute="_compute_construction_kpis", currency_field="currency_id")
    purchase_commitment = fields.Monetary(compute="_compute_construction_kpis", currency_field="currency_id")
    construction_progress = fields.Float(compute="_compute_construction_kpis", string="Progress %")
    boq_count = fields.Integer(compute="_compute_construction_counts")
    material_request_count = fields.Integer(compute="_compute_construction_counts")
    manufacturing_count = fields.Integer(compute="_compute_construction_counts")
    daily_log_count = fields.Integer(compute="_compute_construction_counts")
    change_order_count = fields.Integer(compute="_compute_construction_counts")

    @api.depends("task_ids.construction_progress")
    def _compute_construction_kpis(self):
        Boq = self.env["construction.boq"]
        ChangeOrder = self.env["construction.change.order"]
        PurchaseOrder = self.env["purchase.order"]
        for project in self:
            boqs = Boq.search([("project_id", "=", project.id), ("state", "=", "approved")])
            changes = ChangeOrder.search([("project_id", "=", project.id), ("state", "=", "approved")])
            pos = PurchaseOrder.search([
                ("construction_project_id", "=", project.id),
                ("state", "in", ["purchase", "done"]),
            ])
            construction_tasks = project.task_ids.filtered(lambda t: t.is_construction_task)
            project.approved_boq_amount = sum(boqs.mapped("total_amount"))
            project.variation_amount = sum(changes.mapped("amount_total"))
            project.purchase_commitment = sum(pos.mapped("amount_total"))
            project.construction_progress = (
                sum(construction_tasks.mapped("construction_progress")) / len(construction_tasks)
                if construction_tasks
                else 0.0
            )

    def _compute_construction_counts(self):
        for project in self:
            project.boq_count = self.env["construction.boq"].search_count([("project_id", "=", project.id)])
            project.material_request_count = self.env["construction.material.request"].search_count([("project_id", "=", project.id)])
            project.manufacturing_count = self.env["mrp.production"].search_count([("construction_project_id", "=", project.id)])
            project.daily_log_count = self.env["construction.daily.log"].search_count([("project_id", "=", project.id)])
            project.change_order_count = self.env["construction.change.order"].search_count([("project_id", "=", project.id)])

    def _construction_action(self, name, res_model, domain):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": res_model,
            "view_mode": "list,form",
            "domain": domain,
            "context": {"default_project_id": self.id},
        }

    def action_view_boqs(self):
        return self._construction_action("BOQs", "construction.boq", [("project_id", "=", self.id)])

    def action_view_material_requests(self):
        return self._construction_action("Material Requests", "construction.material.request", [("project_id", "=", self.id)])

    def action_view_manufacturing(self):
        return self._construction_action("Manufacturing Orders", "mrp.production", [("construction_project_id", "=", self.id)])

    def action_view_daily_logs(self):
        return self._construction_action("Daily Logs", "construction.daily.log", [("project_id", "=", self.id)])

    def action_view_change_orders(self):
        return self._construction_action("Change Orders", "construction.change.order", [("project_id", "=", self.id)])


class ProjectTask(models.Model):
    _inherit = "project.task"

    is_construction_task = fields.Boolean(default=False, tracking=True)
    boq_line_id = fields.Many2one("construction.boq.line", string="BOQ Line", ondelete="set null")
    work_category = fields.Selection(
        [
            ("civil", "Civil"),
            ("structural", "Structural"),
            ("architectural", "Architectural"),
            ("mep", "MEP"),
            ("finishing", "Finishing"),
            ("external", "External Works"),
            ("other", "Other"),
        ],
        default="civil",
    )
    planned_qty = fields.Float()
    executed_qty = fields.Float(tracking=True)
    construction_uom_id = fields.Many2one("uom.uom", string="Construction UoM")
    construction_progress = fields.Float(compute="_compute_construction_progress", store=True)

    @api.depends("planned_qty", "executed_qty")
    def _compute_construction_progress(self):
        for task in self:
            if task.planned_qty > 0:
                task.construction_progress = min(100.0, (task.executed_qty / task.planned_qty) * 100.0)
            else:
                task.construction_progress = 0.0

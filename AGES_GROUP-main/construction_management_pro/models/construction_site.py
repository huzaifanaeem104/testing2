from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionDailyLog(models.Model):
    _name = "construction.daily.log"
    _description = "Construction Daily Site Log"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "log_date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    log_date = fields.Date(default=fields.Date.context_today, required=True)
    prepared_by = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    weather = fields.Selection(
        [("clear", "Clear"), ("cloudy", "Cloudy"), ("rain", "Rain"), ("storm", "Storm"), ("hot", "Hot"), ("other", "Other")],
        default="clear",
    )
    manpower = fields.Integer()
    work_completed = fields.Html()
    materials_received = fields.Html()
    equipment_used = fields.Html()
    delays_issues = fields.Html()
    safety_notes = fields.Html()
    visitor_notes = fields.Html()
    attachment_count = fields.Integer(compute="_compute_attachment_count")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.daily.log") or "New"
        return super().create(vals_list)

    def _compute_attachment_count(self):
        Attachment = self.env["ir.attachment"]
        for rec in self:
            rec.attachment_count = Attachment.search_count([("res_model", "=", rec._name), ("res_id", "=", rec.id)])


class ConstructionProgressEntry(models.Model):
    _name = "construction.progress.entry"
    _description = "Construction Progress Measurement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    task_id = fields.Many2one("project.task", required=True, domain="[('project_id', '=', project_id)]")
    boq_line_id = fields.Many2one(related="task_id.boq_line_id", store=True, readonly=True)
    uom_id = fields.Many2one(related="task_id.construction_uom_id", store=True, readonly=True)
    planned_qty = fields.Float(related="task_id.planned_qty", store=True, readonly=True)
    previous_qty = fields.Float(compute="_compute_previous_qty")
    quantity_today = fields.Float(required=True)
    cumulative_qty = fields.Float(compute="_compute_cumulative", store=True)
    progress_percent = fields.Float(compute="_compute_cumulative", store=True)
    state = fields.Selection([("draft", "Draft"), ("approved", "Approved"), ("cancel", "Cancelled")], default="draft", tracking=True)
    notes = fields.Text()

    @api.depends("project_id", "task_id", "date")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s - %s - %s" % (
                rec.project_id.display_name or "Project",
                rec.task_id.display_name or "Task",
                rec.date or "",
            )

    def _compute_previous_qty(self):
        for rec in self:
            domain = [("task_id", "=", rec.task_id.id), ("state", "=", "approved")]
            if rec.id:
                domain.append(("id", "!=", rec.id))
            previous = self.search(domain)
            rec.previous_qty = sum(previous.mapped("quantity_today"))

    @api.depends("quantity_today", "planned_qty", "task_id", "state")
    def _compute_cumulative(self):
        for rec in self:
            approved_domain = [("task_id", "=", rec.task_id.id), ("state", "=", "approved")]
            if rec.id:
                approved_domain.append(("id", "!=", rec.id))
            prior = sum(self.search(approved_domain).mapped("quantity_today")) if rec.task_id else 0.0
            current = rec.quantity_today if rec.state != "cancel" else 0.0
            rec.cumulative_qty = prior + current
            rec.progress_percent = min(100.0, (rec.cumulative_qty / rec.planned_qty * 100.0)) if rec.planned_qty else 0.0

    def action_approve(self):
        for rec in self:
            rec.state = "approved"
            approved_qty = sum(self.search([("task_id", "=", rec.task_id.id), ("state", "=", "approved")]).mapped("quantity_today"))
            rec.task_id.executed_qty = approved_qty

    def action_cancel(self):
        for rec in self:
            rec.state = "cancel"
            if rec.task_id:
                approved_qty = sum(self.search([("task_id", "=", rec.task_id.id), ("state", "=", "approved")]).mapped("quantity_today"))
                rec.task_id.executed_qty = approved_qty

    @api.constrains("quantity_today")
    def _check_quantity_today(self):
        if any(rec.quantity_today < 0 for rec in self):
            raise ValidationError(_("Progress quantity cannot be negative."))


class ConstructionRfi(models.Model):
    _name = "construction.rfi"
    _description = "Construction Request for Information"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, domain="[('is_construction', '=', True)]", tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    task_id = fields.Many2one("project.task", domain="[('project_id', '=', project_id)]")
    subject = fields.Char(required=True, tracking=True)
    question = fields.Html(required=True)
    response = fields.Html()
    raised_by = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    assigned_to = fields.Many2one("res.users", tracking=True)
    due_date = fields.Date()
    state = fields.Selection(
        [("draft", "Draft"), ("open", "Open"), ("answered", "Answered"), ("closed", "Closed"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.rfi") or "New"
        return super().create(vals_list)

    def action_open(self):
        self.write({"state": "open"})

    def action_answered(self):
        for rec in self:
            if not rec.response:
                raise UserError(_("Enter a response before marking the RFI answered."))
            rec.state = "answered"

    def action_close(self):
        self.write({"state": "closed"})

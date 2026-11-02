# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    is_civil_material = fields.Boolean(
        string="Civil Material PO",
        copy=False,
        tracking=True,
        help="When set, use Civil Material Slips for daily trucks (products live on slips, "
        "not on the PO Products tab) and Create monthly bill instead of billing after each GRN.",
    )
    civil_slip_ids = fields.One2many(
        "ages.civil.material.slip",
        "purchase_id",
        string="Civil Material Slips",
    )
    civil_slip_count = fields.Integer(
        string="Slip Count",
        compute="_compute_civil_slip_count",
    )
    civil_slip_qty_total = fields.Float(
        string="Slip Qty Total",
        compute="_compute_civil_slip_totals",
        digits="Product Unit of Measure",
    )
    civil_slip_qty_unbilled = fields.Float(
        string="Unbilled Slip Qty",
        compute="_compute_civil_slip_totals",
        digits="Product Unit of Measure",
    )

    @api.depends("civil_slip_ids")
    def _compute_civil_slip_count(self):
        for order in self:
            order.civil_slip_count = len(order.civil_slip_ids)

    @api.depends(
        "civil_slip_ids",
        "civil_slip_ids.state",
        "civil_slip_ids.qty_total",
        "civil_slip_ids.bill_id",
    )
    def _compute_civil_slip_totals(self):
        for order in self:
            slips = order.civil_slip_ids.filtered(
                lambda s: s.state in ("confirmed", "received", "billed")
            )
            order.civil_slip_qty_total = sum(slips.mapped("qty_total"))
            unbilled = slips.filtered(lambda s: s.state == "received" and not s.bill_id)
            order.civil_slip_qty_unbilled = sum(unbilled.mapped("qty_total"))

    def action_view_civil_slips(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Civil Material Slips"),
            "res_model": "ages.civil.material.slip",
            "view_mode": "list,form",
            "domain": [("purchase_id", "=", self.id)],
            "context": {
                "default_purchase_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_project_id": self.ages_project_id.id
                if "ages_project_id" in self._fields
                else False,
            },
        }
        return action

    def action_create_civil_slip(self):
        self.ensure_one()
        if not self.is_civil_material:
            raise UserError(_("Only Civil Material POs can create Civil Material Slips."))
        if self.state not in ("purchase", "done"):
            raise UserError(_("Confirm the purchase order before creating slips."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Civil Material Slip"),
            "res_model": "ages.civil.material.slip",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_purchase_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_project_id": self.ages_project_id.id
                if "ages_project_id" in self._fields
                else False,
            },
        }

    def action_open_civil_monthly_bill_wizard(self):
        self.ensure_one()
        if not self.is_civil_material:
            raise UserError(_("This action is only for Civil Material POs."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Monthly Bill"),
            "res_model": "ages.civil.monthly.bill.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_id": self.id,
            },
        }

    def action_create_invoice(self):
        civil = self.filtered("is_civil_material")
        if civil and not self.env.context.get("ages_civil_allow_invoice"):
            if len(self) == 1:
                return self.action_open_civil_monthly_bill_wizard()
            raise UserError(
                _(
                    "Civil Material POs cannot use standard Create Bill.\n"
                    "Open each Civil Material PO and use Create monthly bill "
                    "so all truck slips are billed together.\n"
                    "Affected: %s"
                )
                % ", ".join(civil.mapped("name"))
            )
        return super().action_create_invoice()

    def _create_picking(self):
        """No auto receipt on Civil Material POs — GRN is created per slip."""
        non_civil = self.filtered(lambda o: not o.is_civil_material)
        if non_civil:
            return super(PurchaseOrder, non_civil)._create_picking()
        return True

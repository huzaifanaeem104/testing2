# -*- coding: utf-8 -*-

import calendar

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgesCivilMaterialReportWizard(models.TransientModel):
    _name = "ages.civil.material.report.wizard"
    _description = "Civil Material Detail Report Wizard"

    report_mode = fields.Selection(
        [
            ("date_range", "Date Range"),
            ("month", "Month"),
        ],
        string="Report By",
        required=True,
        default="month",
    )
    year = fields.Integer(
        string="Year",
        default=lambda self: fields.Date.context_today(self).year,
    )
    month = fields.Selection(
        [
            ("1", "January"),
            ("2", "February"),
            ("3", "March"),
            ("4", "April"),
            ("5", "May"),
            ("6", "June"),
            ("7", "July"),
            ("8", "August"),
            ("9", "September"),
            ("10", "October"),
            ("11", "November"),
            ("12", "December"),
        ],
        string="Month",
        default=lambda self: str(fields.Date.context_today(self).month),
    )
    date_from = fields.Date(string="From Date")
    date_to = fields.Date(string="To Date")
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        domain="[('supplier_rank', '>', 0)]",
    )
    purchase_id = fields.Many2one(
        "purchase.order",
        string="Civil Material PO",
        domain="[('is_civil_material', '=', True)]",
    )
    project_id = fields.Many2one("project.project", string="Project")
    state_filter = fields.Selection(
        [
            ("all", "All (except cancelled)"),
            ("received_billed", "Received / Billed"),
            ("received", "Received only"),
            ("billed", "Billed only"),
        ],
        string="Slip Status",
        default="received_billed",
        required=True,
    )

    @api.onchange("report_mode", "year", "month")
    def _onchange_month(self):
        if self.report_mode != "month" or not self.year or not self.month:
            return
        month = int(self.month)
        last_day = calendar.monthrange(self.year, month)[1]
        self.date_from = fields.Date.from_string("%04d-%02d-01" % (self.year, month))
        self.date_to = fields.Date.from_string(
            "%04d-%02d-%02d" % (self.year, month, last_day)
        )

    def _get_date_bounds(self):
        self.ensure_one()
        if self.report_mode == "month":
            if not self.year or not self.month:
                raise UserError(_("Select year and month."))
            month = int(self.month)
            last_day = calendar.monthrange(self.year, month)[1]
            date_from = fields.Date.from_string("%04d-%02d-01" % (self.year, month))
            date_to = fields.Date.from_string(
                "%04d-%02d-%02d" % (self.year, month, last_day)
            )
            return date_from, date_to
        if not self.date_from or not self.date_to:
            raise UserError(_("Set From Date and To Date."))
        if self.date_from > self.date_to:
            raise UserError(_("From Date cannot be after To Date."))
        return self.date_from, self.date_to

    def _slip_domain(self):
        self.ensure_one()
        date_from, date_to = self._get_date_bounds()
        domain = [
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("state", "!=", "cancelled"),
        ]
        if self.state_filter == "received_billed":
            domain.append(("state", "in", ("received", "billed")))
        elif self.state_filter == "received":
            domain.append(("state", "=", "received"))
        elif self.state_filter == "billed":
            domain.append(("state", "=", "billed"))
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        if self.purchase_id:
            domain.append(("purchase_id", "=", self.purchase_id.id))
        if self.project_id:
            domain.append(("project_id", "=", self.project_id.id))
        return domain

    def _get_slips(self):
        return self.env["ages.civil.material.slip"].search(
            self._slip_domain(), order="partner_id, purchase_id, date, id"
        )

    def get_report_data(self):
        """Structured data for QWeb: groups by vendor then PO."""
        self.ensure_one()
        date_from, date_to = self._get_date_bounds()
        slips = self._get_slips()
        if not slips:
            raise UserError(_("No civil material slips found for these filters."))

        groups = []
        for partner in slips.mapped("partner_id"):
            partner_slips = slips.filtered(lambda s: s.partner_id == partner)
            po_groups = []
            for po in partner_slips.mapped("purchase_id"):
                po_slips = partner_slips.filtered(lambda s: s.purchase_id == po)
                rows = []
                subtotal = 0.0
                seq = 0
                for slip in po_slips:
                    for line in slip.line_ids:
                        seq += 1
                        amount = line.amount
                        subtotal += amount
                        rows.append(
                            {
                                "seq": seq,
                                "date": slip.date,
                                "description": line.name or (
                                    line.product_id.display_name if line.product_id else ""
                                ),
                                "slip_no": slip.first_measurement_slip or slip.name,
                                "cm_ref": slip.name,
                                "truck_no": slip.truck_no or "",
                                "measurement": line.quantity,
                                "uom": line.product_uom_id.display_name if line.product_uom_id else "",
                                "rate": line.rate,
                                "amount": amount,
                                "length": line.length,
                                "breadth": line.breadth,
                                "height": line.height,
                                "remarks": line.remarks or "",
                            }
                        )
                po_groups.append(
                    {
                        "purchase": po,
                        "project": po.ages_project_id
                        if "ages_project_id" in po._fields
                        else False,
                        "project_name": (
                            po.ages_project_id.display_name
                            if "ages_project_id" in po._fields and po.ages_project_id
                            else (po_slips[:1].project_id.display_name if po_slips[:1].project_id else "")
                        ),
                        "rows": rows,
                        "subtotal": subtotal,
                        "slip_count": len(po_slips),
                    }
                )
            groups.append(
                {
                    "partner": partner,
                    "partner_name": partner.display_name,
                    "partner_address": partner.contact_address or "",
                    "partner_phone": partner.phone or partner.mobile or "",
                    "po_groups": po_groups,
                    "total": sum(g["subtotal"] for g in po_groups),
                }
            )
        return {
            "date_from": date_from,
            "date_to": date_to,
            "groups": groups,
            "grand_total": sum(g["total"] for g in groups),
            "company": self.env.company,
        }

    def action_print_pdf(self):
        self.ensure_one()
        self.get_report_data()  # validate early
        return self.env.ref(
            "ages_civil_material.action_report_ages_civil_material_detail"
        ).report_action(self)

    def action_view_slips(self):
        self.ensure_one()
        slips = self._get_slips()
        return {
            "type": "ir.actions.act_window",
            "name": _("Civil Material Slips"),
            "res_model": "ages.civil.material.slip",
            "view_mode": "list,form",
            "domain": [("id", "in", slips.ids)],
            "target": "current",
        }

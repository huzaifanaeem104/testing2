# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgesCivilMonthlyBillWizard(models.TransientModel):
    _name = "ages.civil.monthly.bill.wizard"
    _description = "Create Monthly Civil Material Bill"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        required=True,
        domain=[("is_civil_material", "=", True)],
    )
    partner_id = fields.Many2one(related="purchase_id.partner_id")
    date_from = fields.Date(string="From Date")
    date_to = fields.Date(string="To Date")
    slip_ids = fields.Many2many(
        "ages.civil.material.slip",
        string="Slips to Bill",
        domain="[('id', 'in', available_slip_ids)]",
    )
    available_slip_ids = fields.Many2many(
        "ages.civil.material.slip",
        compute="_compute_available_slip_ids",
        string="Available Slips",
    )
    bill_date = fields.Date(
        string="Bill Date",
        required=True,
        default=fields.Date.context_today,
    )

    @api.depends("purchase_id", "date_from", "date_to")
    def _compute_available_slip_ids(self):
        Slip = self.env["ages.civil.material.slip"]
        for wiz in self:
            domain = [
                ("purchase_id", "=", wiz.purchase_id.id),
                ("state", "=", "received"),
                ("bill_id", "=", False),
            ]
            if wiz.date_from:
                domain.append(("date", ">=", wiz.date_from))
            if wiz.date_to:
                domain.append(("date", "<=", wiz.date_to))
            wiz.available_slip_ids = Slip.search(domain, order="date, id")

    @api.onchange("purchase_id", "date_from", "date_to")
    def _onchange_select_slips(self):
        self.slip_ids = self.available_slip_ids

    def action_create_bill(self):
        self.ensure_one()
        po = self.purchase_id
        if not po.is_civil_material:
            raise UserError(_("Only Civil Material POs are supported."))
        slips = self.slip_ids or self.available_slip_ids
        if not slips:
            raise UserError(_("No received unbilled slips in this period."))

        # Make sure slip products are synced as PO lines before billing.
        slips._ensure_po_lines_from_slip()

        invoice_vals = po.with_context(ages_civil_allow_invoice=True)._prepare_invoice()
        invoice_vals.update(
            {
                "invoice_date": self.bill_date,
                "date": self.bill_date,
                "ref": _("Civil Material %s") % po.name,
                "ages_is_civil_material_bill": True,
                "invoice_line_ids": [],
            }
        )
        invoice = self.env["account.move"].with_context(
            ages_civil_allow_invoice=True
        ).create(invoice_vals)

        seq = 0
        for slip in slips.sorted(lambda s: (s.date or fields.Date.today(), s.id)):
            for line in slip.line_ids:
                seq += 1
                pol = line.purchase_line_id
                if not pol:
                    raise UserError(
                        _("Slip %s: missing PO line for %s. Re-confirm the slip.")
                        % (slip.name, line.product_id.display_name)
                    )
                rate = line.rate or pol.price_unit
                label = _(
                    "%(seq)s | %(date)s | Truck %(truck)s | Slip %(mslip)s | %(desc)s"
                ) % {
                    "seq": seq,
                    "date": slip.date or "",
                    "truck": slip.truck_no or "-",
                    "mslip": slip.first_measurement_slip or slip.name,
                    "desc": line.name or line.product_id.display_name,
                }
                line_vals = {
                    "move_id": invoice.id,
                    "product_id": line.product_id.id,
                    "name": label,
                    "quantity": line.quantity,
                    "product_uom_id": line.product_uom_id.id,
                    "price_unit": rate,
                    "purchase_line_id": pol.id,
                    "ages_civil_slip_id": slip.id,
                    "ages_civil_truck_no": slip.truck_no,
                    "ages_civil_measurement_slip": slip.first_measurement_slip or slip.name,
                    "ages_civil_slip_date": slip.date,
                }
                if pol.taxes_id:
                    line_vals["tax_ids"] = [(6, 0, pol.taxes_id.ids)]
                elif line.product_id.supplier_taxes_id:
                    line_vals["tax_ids"] = [
                        (6, 0, line.product_id.supplier_taxes_id.ids)
                    ]
                self.env["account.move.line"].create(line_vals)

            slip.write({"bill_id": invoice.id, "state": "billed"})

        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bill"),
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "target": "current",
        }

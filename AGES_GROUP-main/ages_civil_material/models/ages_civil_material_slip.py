# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class AgesCivilMaterialSlip(models.Model):
    _name = "ages.civil.material.slip"
    _description = "Civil Material Slip"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Slip Reference",
        required=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )
    purchase_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        required=True,
        domain=[("is_civil_material", "=", True), ("state", "in", ("purchase", "done"))],
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    arrival_time = fields.Float(
        string="Time",
        help="Arrival time (e.g. 12.5 = 12:30).",
    )
    truck_no = fields.Char(string="Truck / Trolley #", tracking=True)
    first_measurement_slip = fields.Char(
        string="First Measurement Slip",
        tracking=True,
    )
    remarks = fields.Text(string="Header Remarks")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("received", "Received"),
            ("billed", "Billed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        "ages.civil.material.slip.line",
        "slip_id",
        string="Lines",
        copy=True,
    )
    qty_total = fields.Float(
        string="Total Quantity",
        compute="_compute_qty_total",
        store=True,
        digits="Product Unit of Measure",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="GRN",
        copy=False,
        readonly=True,
    )
    gate_pass_id = fields.Many2one(
        "ages.gate.pass",
        string="Gate Pass",
        copy=False,
        readonly=True,
    )
    bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        copy=False,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="purchase_id.currency_id",
        store=True,
    )

    @api.depends("line_ids.quantity")
    def _compute_qty_total(self):
        for slip in self:
            slip.qty_total = sum(slip.line_ids.mapped("quantity"))

    @api.onchange("purchase_id")
    def _onchange_purchase_id(self):
        if not self.purchase_id:
            return
        self.partner_id = self.purchase_id.partner_id
        self.company_id = self.purchase_id.company_id
        if "ages_project_id" in self.purchase_id._fields:
            self.project_id = self.purchase_id.ages_project_id
        # Civil Material POs have no product lines — products live on slips only.

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) in (_("New"), "New", False):
                vals["name"] = sequence.next_by_code("ages.civil.material.slip") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for slip in self:
            if slip.state != "draft":
                raise UserError(_("Only draft slips can be confirmed."))
            if not slip.line_ids:
                raise UserError(_("Add at least one measurement line."))
            if any(float_is_zero(l.quantity, precision_digits=4) for l in slip.line_ids):
                raise UserError(_("Each line must have a quantity (from L×B×H or manual)."))
            if any(not l.product_id for l in slip.line_ids):
                raise UserError(_("Each measurement line needs a product / material."))
            if not slip.purchase_id.is_civil_material:
                raise UserError(_("The purchase order must be a Civil Material PO."))
            slip.line_ids._check_uom_compatible_with_product()
            # Slip products become / update the PO lines (source of truth for stock + bill).
            # Do not let purchase_stock auto-create a PO receipt — GRN is per slip.
            slip.with_context(ages_civil_skip_picking=True)._ensure_po_lines_from_slip()
            slip._cancel_orphan_po_pickings()
            slip.state = "confirmed"
        return True

    def _cancel_orphan_po_pickings(self):
        """Cancel standard PO receipts that are not linked to any civil slip.

        Adding PO lines normally creates a Ready receipt (origin = PO name).
        Civil Material uses only slip GRNs (origin = PO / slip).
        """
        for slip in self:
            po = slip.purchase_id
            if not po:
                continue
            slip_picking_ids = set(po.civil_slip_ids.mapped("picking_id").ids)
            orphans = po.picking_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
                and p.id not in slip_picking_ids
            )
            if orphans:
                orphans.action_cancel()

    def action_reset_draft(self):
        for slip in self:
            if slip.state not in ("confirmed", "cancelled"):
                raise UserError(_("Only confirmed or cancelled slips can reset to draft."))
            if slip.picking_id or slip.gate_pass_id:
                raise UserError(_("Remove / cancel GRN and gate pass before resetting."))
            slip.state = "draft"
        return True

    def action_cancel(self):
        for slip in self:
            if slip.state == "billed":
                raise UserError(_("Billed slips cannot be cancelled."))
            if slip.picking_id and slip.picking_id.state == "done":
                raise UserError(_("Cancel or reverse the GRN before cancelling the slip."))
            slip.state = "cancelled"
        return True

    def action_create_grn(self):
        """Create a partial incoming picking for this slip's quantities."""
        self.ensure_one()
        if self.state not in ("confirmed", "received"):
            raise UserError(_("Confirm the slip before creating a GRN."))
        if self.picking_id:
            return self._action_open_picking()

        po = self.purchase_id
        if po.state not in ("purchase", "done"):
            raise UserError(_("Purchase order must be confirmed."))

        picking_type = po.picking_type_id
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "incoming"),
                    ("warehouse_id.company_id", "=", po.company_id.id),
                ],
                limit=1,
            )
        if not picking_type:
            raise UserError(_("No incoming operation type found for this company."))

        location_src = picking_type.default_location_src_id or self.env.ref(
            "stock.stock_location_suppliers", raise_if_not_found=False
        )
        location_dest = picking_type.default_location_dest_id
        if not location_src or not location_dest:
            raise UserError(_("Incoming operation type is missing source/destination locations."))

        # Slip products act as PO lines → stock moves against those lines.
        # Skip standard PO auto-receipt (that would create a second transfer).
        self.line_ids._check_uom_compatible_with_product()
        self.with_context(ages_civil_skip_picking=True)._ensure_po_lines_from_slip()
        self._cancel_orphan_po_pickings()
        move_cmds = []
        for line in self.line_ids:
            if float_compare(
                line.quantity,
                0.0,
                precision_rounding=line.product_uom_id.rounding or 0.01,
            ) <= 0:
                continue
            if line.product_id.type == "service":
                raise UserError(
                    _(
                        "Cannot create GRN for service product %s. "
                        "Use a storable/consumable material on the slip."
                    )
                    % line.product_id.display_name
                )
            if not line.purchase_line_id:
                raise UserError(
                    _("Could not create/link a PO line for product %s.")
                    % line.product_id.display_name
                )
            move_cmds.append(
                (
                    0,
                    0,
                    {
                        "name": line.name or line.product_id.display_name,
                        "product_id": line.product_id.id,
                        "product_uom": line.product_uom_id.id,
                        "product_uom_qty": line.quantity,
                        "quantity": line.quantity,
                        "location_id": location_src.id,
                        "location_dest_id": location_dest.id,
                        "purchase_line_id": line.purchase_line_id.id,
                        "description_picking": self._move_description(line),
                    },
                )
            )
        if not move_cmds:
            raise UserError(_("No positive quantities to receive."))

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": self.partner_id.id,
                "origin": "%s / %s" % (po.name, self.name),
                "location_id": location_src.id,
                "location_dest_id": location_dest.id,
                "company_id": po.company_id.id,
                "scheduled_date": fields.Datetime.to_datetime(self.date)
                if self.date
                else fields.Datetime.now(),
                "move_ids": move_cmds,
            }
        )
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        self.picking_id = picking.id
        return self._action_open_picking()

    def _ensure_po_lines_from_slip(self):
        """Create/update PO lines from this slip's products.

        On Civil Material POs the user does not enter Products on the PO.
        Slip measurement lines are the source of truth and become the PO lines
        used for GRN (stock move) and monthly vendor bill.
        """
        PurchaseLine = self.env["purchase.order.line"]
        for slip in self:
            po = slip.purchase_id
            if not po:
                continue
            for line in slip.line_ids:
                if not line.product_id or float_is_zero(line.quantity, precision_digits=4):
                    continue
                pol = line.purchase_line_id
                if (
                    not pol
                    or pol.order_id != po
                    or pol.product_id != line.product_id
                ):
                    pol = po.order_line.filtered(
                        lambda l, product=line.product_id: l.product_id == product
                        and not l.display_type
                    )[:1]
                if not pol:
                    date_planned = (
                        fields.Datetime.to_datetime(slip.date)
                        if slip.date
                        else fields.Datetime.now()
                    )
                    pol = PurchaseLine.with_context(
                        ages_civil_skip_picking=True
                    ).create(
                        {
                            "order_id": po.id,
                            "product_id": line.product_id.id,
                            "name": line.name or line.product_id.display_name,
                            "product_qty": line.quantity,
                            "product_uom": line.product_uom_id.id
                            or line.product_id.uom_id.id,
                            "price_unit": line.rate or 0.0,
                            "date_planned": date_planned,
                        }
                    )
                else:
                    # Ordered qty = all non-cancelled slip qtys for this product on the PO
                    total_slip_qty = sum(
                        po.civil_slip_ids.filtered(
                            lambda s: s.state != "cancelled"
                        )
                        .mapped("line_ids")
                        .filtered(lambda l, product=line.product_id: l.product_id == product)
                        .mapped("quantity")
                    )
                    # Include current line if not yet saved in civil_slip_ids relation edge cases
                    if line.slip_id not in po.civil_slip_ids:
                        total_slip_qty += line.quantity
                    new_qty = max(total_slip_qty, pol.qty_received or 0.0)
                    vals = {}
                    if float_compare(
                        pol.product_qty,
                        new_qty,
                        precision_rounding=pol.product_uom.rounding or 0.01,
                    ) < 0:
                        vals["product_qty"] = new_qty
                    if line.rate and float_is_zero(pol.price_unit, precision_digits=4):
                        vals["price_unit"] = line.rate
                    if vals:
                        pol.with_context(ages_civil_skip_picking=True).write(vals)
                if line.purchase_line_id != pol or (
                    not line.rate and pol.price_unit
                ):
                    link_vals = {}
                    if line.purchase_line_id != pol:
                        link_vals["purchase_line_id"] = pol.id
                    if not line.rate and pol.price_unit:
                        link_vals["rate"] = pol.price_unit
                    if link_vals:
                        line.with_context(ages_civil_skip_po_link=True).write(link_vals)

    def _move_description(self, line):
        parts = [
            self.name,
            self.truck_no and _("Truck %s") % self.truck_no,
            self.first_measurement_slip
            and _("Meas. slip %s") % self.first_measurement_slip,
            line.length
            and _("L=%s B=%s H=%s")
            % (line.length_display, line.breadth_display, line.height_display),
        ]
        return " | ".join(p for p in parts if p)

    def _action_open_picking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("GRN"),
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_gate_pass(self):
        self.ensure_one()
        if not self.picking_id:
            self.action_create_grn()
        if self.gate_pass_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Gate Pass"),
                "res_model": "ages.gate.pass",
                "res_id": self.gate_pass_id.id,
                "view_mode": "form",
                "target": "current",
            }
        picking = self.picking_id
        if picking.state in ("done", "cancel"):
            raise UserError(
                _("Create the gate pass while the GRN is still Draft/Ready.")
            )
        action = picking.action_create_gate_pass()
        gate_pass = self.env["ages.gate.pass"].browse(action.get("res_id"))
        if gate_pass:
            vals = {}
            if self.truck_no and "truck_no" in gate_pass._fields:
                vals["truck_no"] = self.truck_no
            if vals:
                gate_pass.write(vals)
            self.gate_pass_id = gate_pass.id
        return action

    def action_mark_received(self):
        """After GRN is validated, mark slip received (stock in, not billed)."""
        for slip in self:
            if not slip.picking_id:
                raise UserError(_("Create and validate a GRN first."))
            if slip.picking_id.state != "done":
                raise UserError(
                    _("Validate GRN %s before marking the slip as received.")
                    % slip.picking_id.name
                )
            if slip.state not in ("confirmed", "received"):
                raise UserError(_("Slip must be confirmed first."))
            slip.state = "received"
        return True

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("No GRN linked."))
        return self._action_open_picking()

    def action_view_gate_pass(self):
        self.ensure_one()
        if not self.gate_pass_id:
            raise UserError(_("No gate pass linked."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Gate Pass"),
            "res_model": "ages.gate.pass",
            "res_id": self.gate_pass_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_("No vendor bill linked."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bill"),
            "res_model": "account.move",
            "res_id": self.bill_id.id,
            "view_mode": "form",
            "target": "current",
        }


class AgesCivilMaterialSlipLine(models.Model):
    _name = "ages.civil.material.slip.line"
    _description = "Civil Material Slip Line"
    _order = "id"

    slip_id = fields.Many2one(
        "ages.civil.material.slip",
        string="Slip",
        required=True,
        ondelete="cascade",
        index=True,
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="PO Line",
        domain="[('order_id', '=', parent.purchase_id)]",
        help="Optional. Civil Material POs usually have no product lines; "
        "the slip product is used for GRN and billing.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain="[('purchase_ok', '=', True)]",
    )
    name = fields.Char(string="Description", required=True)
    length = fields.Float(string="L (ft)", digits=(16, 4))
    breadth = fields.Float(string="B (ft)", digits=(16, 4))
    height = fields.Float(string="H (ft)", digits=(16, 4))
    length_display = fields.Char(string="L", compute="_compute_dim_display")
    breadth_display = fields.Char(string="B", compute="_compute_dim_display")
    height_display = fields.Char(string="H", compute="_compute_dim_display")
    quantity = fields.Float(
        string="Quantity",
        digits="Product Unit of Measure",
        required=True,
        default=0.0,
        help="Auto-fills as L×B×H (cubic feet). You can override manually.",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit",
        required=True,
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    product_uom_category_id = fields.Many2one(
        related="product_id.uom_id.category_id",
        string="UoM Category",
    )
    rate = fields.Float(string="Rate", digits="Product Price")
    amount = fields.Monetary(
        string="Amount",
        compute="_compute_amount",
        store=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(related="slip_id.currency_id")
    remarks = fields.Char(string="Remarks")

    @api.depends("length", "breadth", "height")
    def _compute_dim_display(self):
        for line in self:
            line.length_display = self._format_dim(line.length)
            line.breadth_display = self._format_dim(line.breadth)
            line.height_display = self._format_dim(line.height)

    @staticmethod
    def _format_dim(value):
        if not value:
            return ""
        return ("%g" % value).rstrip("0").rstrip(".") if isinstance(value, float) else str(value)

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.rate

    def _qty_from_dimensions(self, length, breadth, height):
        if length and breadth and height:
            return float_round(length * breadth * height, precision_digits=2)
        return False

    @api.onchange("length", "breadth", "height")
    def _onchange_dimensions(self):
        for line in self:
            qty = line._qty_from_dimensions(line.length, line.breadth, line.height)
            if qty is not False:
                line.quantity = qty

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.product_uom_id = self.product_id.uom_po_id or self.product_id.uom_id
            if self.slip_id.purchase_id:
                pol = self.slip_id.purchase_id.order_line.filtered(
                    lambda l: l.product_id == self.product_id
                )[:1]
                if pol:
                    self.purchase_line_id = pol
                    self.rate = pol.price_unit
                    self.product_uom_id = pol.product_uom
                    self.name = pol.name
                else:
                    self.purchase_line_id = False
            warning = self._uom_volume_warning()
            if warning:
                return warning

    def _uom_volume_warning(self):
        """L×B×H is volumetric — warn if product UoM is not in a volume category."""
        self.ensure_one()
        if not (self.length and self.breadth and self.height and self.product_uom_id):
            return False
        # Common volume UoM names; category check is authoritative via _check_uom.
        name = (self.product_uom_id.category_id.name or "").lower()
        uom_name = (self.product_uom_id.name or "").lower()
        looks_volume = (
            "volume" in name
            or "cubic" in uom_name
            or "cft" in uom_name
            or "cu.ft" in uom_name
            or "m3" in uom_name
            or "m³" in uom_name
        )
        if looks_volume:
            return False
        return {
            "warning": {
                "title": _("Unit of measure mismatch"),
                "message": _(
                    "This slip line uses L×B×H (volume), but product %(product)s "
                    "uses unit %(uom)s (category: %(cat)s).\n\n"
                    "For civil material volume, use a product whose Unit is "
                    "CUBIC FEET (or another Volume UoM), e.g. SAND SUI — not BAGS."
                )
                % {
                    "product": self.product_id.display_name,
                    "uom": self.product_uom_id.display_name,
                    "cat": self.product_uom_id.category_id.display_name,
                },
            }
        }

    def _check_uom_compatible_with_product(self):
        """Block Confirm/GRN when slip UoM category ≠ product UoM category."""
        for line in self:
            if not line.product_id or not line.product_uom_id:
                continue
            product_uom = line.product_id.uom_id
            if line.product_uom_id.category_id != product_uom.category_id:
                raise UserError(
                    _(
                        "Slip line for %(product)s: unit %(line_uom)s does not match "
                        "product unit %(product_uom)s (different categories: "
                        "%(line_cat)s vs %(product_cat)s).\n\n"
                        "Fix one of these:\n"
                        "• Use product whose Unit is CUBIC FEET (Volume), or\n"
                        "• On the product, set Unit / Purchase Unit to CUBIC FEET, or\n"
                        "• On the slip line, set Unit to a UoM in the same category "
                        "as the product (not recommended for L×B×H volume)."
                    )
                    % {
                        "product": line.product_id.display_name,
                        "line_uom": line.product_uom_id.display_name,
                        "product_uom": product_uom.display_name,
                        "line_cat": line.product_uom_id.category_id.display_name,
                        "product_cat": product_uom.category_id.display_name,
                    }
                )

    def _link_po_line(self):
        """Link to an existing PO line for the same product when present.

        Never writes False in a loop — that caused max recursion on Save when the
        Civil Material PO still had no product lines.
        """
        if self.env.context.get("ages_civil_skip_po_link"):
            return
        for line in self:
            po = line.slip_id.purchase_id
            if not po or not line.product_id:
                continue
            if (
                line.purchase_line_id
                and line.purchase_line_id.order_id == po
                and line.purchase_line_id.product_id == line.product_id
            ):
                continue
            pol = po.order_line.filtered(
                lambda l, product=line.product_id: l.product_id == product
                and not l.display_type
            )[:1]
            if not pol:
                continue
            vals = {"purchase_line_id": pol.id}
            if not line.rate and pol.price_unit:
                vals["rate"] = pol.price_unit
            line.with_context(ages_civil_skip_po_link=True).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            qty = self._qty_from_dimensions(
                vals.get("length"), vals.get("breadth"), vals.get("height")
            )
            if qty is not False and not vals.get("quantity"):
                vals["quantity"] = qty
        lines = super().create(vals_list)
        lines._link_po_line()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("ages_civil_skip_po_link"):
            return res
        dim_keys = {"length", "breadth", "height"}
        if dim_keys & set(vals) and "quantity" not in vals:
            for line in self:
                qty = line._qty_from_dimensions(line.length, line.breadth, line.height)
                if qty is not False:
                    super(AgesCivilMaterialSlipLine, line).write({"quantity": qty})
        # Relink only when product changes — not on every purchase_line_id write.
        if "product_id" in vals or dim_keys & set(vals):
            self._link_po_line()
        return res

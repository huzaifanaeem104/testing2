# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class AccountPaymentWithholdingLine(models.Model):
    """Inherit account.payment.withholding.line: auto sequence 0, 1, 2... and renumber on delete."""

    _inherit = "account.payment.withholding.line"

    @api.model
    def default_get(self, fields_list):
        """Set name (Sequence N) to next position 0, 1, 2... when adding a line."""
        res = super().default_get(fields_list)
        if res.get("name"):
            return res
        payment = self._get_payment_for_sequence_from_vals(res)
        if payment and payment.exists():
            res["name"] = self._next_sequence_for_payment(payment)
        return res

    @api.model
    def _next_sequence_for_payment(self, payment):
        """Return next sequence number (0, 1, 2...) for payment's withholding lines."""
        line_field = (
            "withholding_line_ids"
            if hasattr(payment, "withholding_line_ids")
            else "payment_withholding_line_ids"
        )
        if not hasattr(payment, line_field):
            return "0"
        return str(len(payment[line_field]))

    @api.model_create_multi
    def create(self, vals_list):
        """Assign name 0, 1, 2... for payment withholding lines."""
        if not vals_list:
            return super().create(vals_list)
        payment = self._get_payment_for_sequence_from_vals(vals_list[0])
        if payment and payment.exists():
            line_field = (
                "withholding_line_ids"
                if hasattr(payment, "withholding_line_ids")
                else "payment_withholding_line_ids"
            )
            if hasattr(payment, line_field):
                existing_count = len(
                    payment[line_field].filtered(
                        lambda l: l.id and isinstance(l.id, int)
                    )
                )
                for index, vals in enumerate(vals_list):
                    if not vals.get("name"):
                        vals["name"] = str(existing_count + index)
        return super().create(vals_list)

    def unlink(self):
        """Renumber remaining lines to 0, 1, 2... after delete."""
        payments_to_renumber = []
        for line in self:
            payment = line._get_payment_for_sequence()
            if payment and payment.exists() and line.id:
                payments_to_renumber.append(payment)
        result = super().unlink()
        seen = set()
        for payment in payments_to_renumber:
            if payment.id in seen:
                continue
            seen.add(payment.id)
            line_field = (
                "withholding_line_ids"
                if hasattr(payment, "withholding_line_ids")
                else "payment_withholding_line_ids"
            )
            if not hasattr(payment, line_field):
                continue
            for idx, line in enumerate(payment[line_field].sorted(key=lambda l: l.id or 0), start=1):
                if line.name != str(idx):
                    line.name = str(idx)
        return result

    def _get_payment_for_sequence(self):
        """Get account.payment for this line (for default_get / unlink)."""
        self.ensure_one()
        if hasattr(self, "payment_id") and self.payment_id:
            return self.payment_id
        if hasattr(self, "parent_id") and self.parent_id and self.parent_id._name == "account.payment":
            return self.parent_id
        if "active_model" in self.env.context and self.env.context.get("active_model") == "account.payment":
            aid = self.env.context.get("active_id")
            if aid:
                return self.env["account.payment"].browse(aid)
        for key in ("default_payment_id", "default_parent_id"):
            pay_id = self.env.context.get(key)
            if pay_id:
                return self.env["account.payment"].browse(pay_id)
        if self.id:
            for field in ("withholding_line_ids", "payment_withholding_line_ids"):
                if hasattr(self.env["account.payment"], field):
                    payment = self.env["account.payment"].search([(field, "in", self.ids)], limit=1)
                    if payment:
                        return payment
        return self.env["account.payment"]

    @api.model
    def _get_payment_for_sequence_from_vals(self, vals):
        """Get account.payment from context or vals (for create/default_get)."""
        vals = vals or {}
        # From vals (set by form / create)
        for fname in ("payment_id", "parent_id", "payment_line_id"):
            if vals.get(fname):
                p = self.env["account.payment"].browse(vals[fname])
                if p.exists():
                    return p
        # From context: active record when form is on payment
        if self.env.context.get("active_model") == "account.payment" and self.env.context.get("active_id"):
            return self.env["account.payment"].browse(self.env.context["active_id"])
        # From context: default_<inverse_field> when adding line from One2many
        for key in ("default_payment_id", "default_parent_id", "default_payment_line_id"):
            pay_id = self.env.context.get(key)
            if pay_id:
                return self.env["account.payment"].browse(pay_id)
        # Discover inverse field: any Many2one to account.payment on this model
        Payment = self.env["account.payment"]
        for fname, field in self._fields.items():
            if field.type == "many2one" and field.comodel_name == "account.payment":
                pay_id = self.env.context.get("default_" + fname) or vals.get(fname)
                if pay_id:
                    p = Payment.browse(pay_id)
                    if p.exists():
                        return p
        # Fallback: any default_* in context that points to an account.payment with withholding lines
        for key, value in self.env.context.items():
            if key.startswith("default_") and isinstance(value, int) and value > 0:
                p = self.env["account.payment"].browse(value)
                if p.exists() and (
                    getattr(p, "withholding_line_ids", None) is not None
                    or getattr(p, "payment_withholding_line_ids", None) is not None
                ):
                    return p
        return self.env["account.payment"]

    @api.onchange("payment_id", "parent_id")
    def _onchange_payment_set_sequence(self):
        """When payment/parent is set and name is empty, set sequence 0, 1, 2... (for UI)."""
        payment = self.env["account.payment"]
        if hasattr(self, "payment_id") and self.payment_id:
            payment = self.payment_id
        elif hasattr(self, "parent_id") and self.parent_id and self.parent_id._name == "account.payment":
            payment = self.parent_id
        if payment and payment.exists() and not self.name:
            self.name = self._next_sequence_for_payment(payment)

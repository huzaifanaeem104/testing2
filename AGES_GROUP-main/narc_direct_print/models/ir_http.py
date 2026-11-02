from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        params = self.env["ir.config_parameter"].sudo()
        enabled = params.get_param("narc_direct_print.enabled", "True")
        result["narc_direct_print"] = str(enabled).lower() not in {"0", "false", "off"}
        result["narc_direct_print_printer"] = (
            params.get_param("narc_direct_print.printer_name") or ""
        )
        result["narc_direct_print_reports"] = (
            self.env["ir.actions.report"]
            .sudo()
            .search([("report_print_behavior", "=", "direct_print")])
            .mapped("report_name")
        )
        return result

from odoo import api, fields, models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    report_print_behavior = fields.Selection(
        selection=[
            ("download", "Download PDF"),
            ("direct_print", "Print"),
        ],
        string="Default behavior",
        default="download",
        help="Download PDF: keep the standard Odoo file download. "
        "Print: send this report to the workstation printer.",
    )

    def _auto_init(self):
        super()._auto_init()
        cr = self.env.cr
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'ir_act_report'
               AND column_name = 'report_print_behavior'
            """
        )
        if not cr.fetchone():
            return
        param = self.env["ir.config_parameter"].sudo()
        if param.get_param("narc_direct_print.opt_in_defaults"):
            return
        cr.execute(
            """
            UPDATE ir_act_report
               SET report_print_behavior = 'download'
             WHERE report_print_behavior IS DISTINCT FROM 'download'
            """
        )
        param.set_param("narc_direct_print.opt_in_defaults", "1")

    def _get_readable_fields(self):
        return super()._get_readable_fields() | {"report_print_behavior"}

    def report_action(self, docids, data=None, config=True):
        action = super().report_action(docids, data=data, config=config)
        return self._inject_direct_print(action)

    def _inject_direct_print(self, action):
        if not action:
            return action
        if action.get("type") != "ir.actions.report":
            context = action.get("context") or {}
            if isinstance(context, dict):
                nested = context.get("report_action")
                if isinstance(nested, dict):
                    self._inject_direct_print(nested)
            return action
        action["id"] = action.get("id") or self.id
        action["report_print_behavior"] = (
            action.get("report_print_behavior") or self.report_print_behavior or "download"
        )
        return action

    @api.model
    def _reset_reports_to_download(self):
        self.with_context(active_test=False).search(
            [("report_print_behavior", "!=", "download")]
        ).write({"report_print_behavior": "download"})

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    narc_direct_print_enabled = fields.Boolean(
        string="Enable direct print",
        config_parameter="narc_direct_print.enabled",
        default=True,
        help="When enabled, reports whose Default behavior is Print are sent "
        "to the workstation printer. All other reports still download as PDF.",
    )
    narc_direct_print_printer = fields.Char(
        string="Preferred printer",
        config_parameter="narc_direct_print.printer_name",
        help="Exact printer name from the computer (for example "
        "HP_LaserJet_MFP_M227sdn_2442AE). Leave empty to use the first "
        "real printer and skip Print to File.",
    )

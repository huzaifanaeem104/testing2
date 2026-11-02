# -*- coding: utf-8 -*-

from odoo import api, models

from odoo.addons.ages_custom_reports.report.report_branding import (
    get_ages_branding_values,
    pdf_format_amount,
)


class ReportCivilMaterialDetail(models.AbstractModel):
    _name = "report.ages_civil_material.report_civil_material_detail"
    _description = "Civil Material Detail Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env["ages.civil.material.report.wizard"].browse(docids)
        reports = []
        for wiz in wizards:
            payload = wiz.get_report_data()
            # Format amounts with shared AGES helper for template
            for grp in payload["groups"]:
                for pog in grp["po_groups"]:
                    for row in pog["rows"]:
                        row["measurement_display"] = "%.2f" % row["measurement"]
                        row["rate_display"] = pdf_format_amount(row["rate"])
                        row["amount_display"] = pdf_format_amount(row["amount"])
                    pog["subtotal_display"] = pdf_format_amount(pog["subtotal"])
                grp["total_display"] = pdf_format_amount(grp["total"])
            payload["grand_total_display"] = pdf_format_amount(payload["grand_total"])
            reports.append({"wizard": wiz, "data": payload})

        subtitle = ""
        if reports:
            first = reports[0]["data"]
            subtitle = "%s — %s" % (first["date_from"], first["date_to"])
        return {
            "doc_ids": docids,
            "doc_model": "ages.civil.material.report.wizard",
            "docs": wizards,
            "reports": reports,
            "report_title": "Civil Material Detail Report",
            "report_subtitle": subtitle,
            **get_ages_branding_values(),
        }


class ReportCivilMaterialStatement(models.AbstractModel):
    _name = "report.ages_civil_material.report_civil_material_statement"
    _description = "Civil Material Statement (PO)"

    @api.model
    def _get_report_values(self, docids, data=None):
        orders = self.env["purchase.order"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "purchase.order",
            "docs": orders,
            "report_title": "Civil Material Statement",
            "report_subtitle": "",
            **get_ages_branding_values(),
        }

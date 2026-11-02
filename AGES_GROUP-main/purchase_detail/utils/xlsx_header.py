from odoo.modules.module import get_module_resource

MODULE_NAME = "purchase_detail"
COMPANY_NAME = "Allah Wale Foundation"
DATA_START_ROW = 5


def _format_report_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _get_logo_path():
    for name in ("awt_logo.png", "awt_logo.jpeg", "awt_logo.jpg"):
        path = get_module_resource(MODULE_NAME, "static/img", name)
        if path:
            return path
    return None


def write_awt_excel_header(sheet, workbook, report_name, date_from=None, date_to=None, as_at_date=None):
    """Write standard AWT header on rows 1-3 and return the first data row index."""
    sheet.set_row(0, 30)
    sheet.set_row(1, 22)
    sheet.set_row(2, 22)
    sheet.set_column("A:C", 18)

    logo_path = _get_logo_path()
    if logo_path:
        sheet.insert_image(0, 0, logo_path, {
            "x_offset": 5,
            "y_offset": 5,
            "x_scale": 0.07,
            "y_scale": 0.07,
        })

    company_fmt = workbook.add_format({"bold": True, "font_size": 14, "valign": "vcenter"})
    report_fmt = workbook.add_format({"bold": True, "font_size": 12, "valign": "vcenter"})
    date_fmt = workbook.add_format({"valign": "vcenter"})

    sheet.write(0, 3, COMPANY_NAME, company_fmt)
    sheet.write(1, 3, report_name or "", report_fmt)

    if as_at_date is not None:
        sheet.write(2, 2, f"As at Date: {_format_report_date(as_at_date)}", date_fmt)
    else:
        sheet.write(2, 2, f"Date From: {_format_report_date(date_from)}", date_fmt)
        sheet.write(2, 6, f"Date To: {_format_report_date(date_to)}", date_fmt)

    return DATA_START_ROW

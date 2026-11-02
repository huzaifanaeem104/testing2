# -*- coding: utf-8 -*-

import base64
import os

from odoo import models
from odoo.modules.module import get_module_resource

AGES_COMPANY_NAME = 'Alhamd General Engineering Services'
AGES_COMPANY_ADDRESS = '55-A Muhafiz Town Lahore Pakistan'
AGES_COMPANY_EMAIL = 'alhamd@alhamdges.com.pk'

# AGES logo palette — deep maroon / red (matches ages_logo.png)
AGES_COLOR_PRIMARY = '#8B1A1A'
AGES_COLOR_PRIMARY_DARK = '#6E1414'
AGES_COLOR_ACCENT = '#B22234'
AGES_COLOR_SECTION = '#FAF0F1'
AGES_COLOR_BORDER = '#EED6DA'
AGES_COLOR_EMAIL = '#8B1A1A'
AGES_COLOR_SUBTITLE = '#F8E8EA'
AGES_ROW_HEIGHT = 24
AGES_XLSX_BODY_FONT_SIZE = 12
AGES_XLSX_TABLE_HEADER_FONT_SIZE = 12

# Shared Excel column widths for text-heavy ledger columns
AGES_XLSX_COL_DATE = 12
AGES_XLSX_COL_JE = 22
AGES_XLSX_COL_PARTNER = 32
AGES_XLSX_COL_LABEL = 36
AGES_XLSX_COL_ACCOUNT = 40
AGES_XLSX_COL_ANALYTIC = 28
AGES_XLSX_COL_AMOUNT = 14
AGES_XLSX_COL_NAME_WIDE = 70

# Legacy alias used by existing xlsx format builders
AGES_COLOR_NAVY = AGES_COLOR_PRIMARY


def pdf_safe_warnings(warnings, data=None):
    """Strip informational banners from PDF output; keep them in HTML preview."""
    report_type = (data or {}).get('report_type', '')
    if report_type in ('pdf', 'qweb-pdf'):
        return []
    return warnings or []


def pdf_hierarchy_row_class(line):
    """CSS classes for hierarchical financial report PDF rows."""
    line_type = line.get('line_type', 'account')
    level = min(line.get('level', 0), 6)
    return f'{line_type} lvl-{level}'


def pdf_hierarchy_indent_px(line, base=8, step=14):
    return base + line.get('level', 0) * step


def enrich_pdf_hierarchy_lines(lines):
    """Add PDF presentation hints used by shared QWeb hierarchy templates."""
    for line in lines:
        line['pdf_row_class'] = pdf_hierarchy_row_class(line)
        line['pdf_indent_px'] = pdf_hierarchy_indent_px(line)
    return lines


def group_ledger_lines(flat_lines, header_type='partner'):
    """Group flat partner/general ledger lines for PDL-style PDF layout."""
    groups = []
    grand_total = None
    current = None
    for line in flat_lines:
        line_type = line.get('line_type')
        if line_type == 'total':
            if current:
                groups.append(current)
                current = None
            grand_total = line
            continue
        if line_type == header_type:
            if current:
                groups.append(current)
            current = {'header': line, 'details': []}
        elif current is not None:
            current['details'].append(line)
    if current:
        groups.append(current)
    return groups, grand_total


def pdf_format_amount(amount):
    """Format PDF amounts with thousands separators and no currency symbol."""
    try:
        value = float(amount or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return '{:,.2f}'.format(value)


def get_ages_branding_values():
    logo_b64 = ''
    logo_path = get_module_resource(
        'ages_custom_reports', 'static/src/img', 'ages_logo.png'
    )
    if logo_path and os.path.isfile(logo_path):
        with open(logo_path, 'rb') as logo_file:
            logo_b64 = base64.b64encode(logo_file.read()).decode()
    return {
        'ages_company_name': AGES_COMPANY_NAME,
        'ages_company_address': AGES_COMPANY_ADDRESS,
        'ages_company_email': AGES_COMPANY_EMAIL,
        'ages_logo': logo_b64,
        'pdf_format_amount': pdf_format_amount,
    }


class AgesReportXlsxMixin(models.AbstractModel):
    _name = 'report.ages_custom_reports.xlsx.mixin'
    _description = 'Shared AGES Excel report branding'

    def _ages_logo_path(self):
        return get_module_resource(
            'ages_custom_reports', 'static/src/img', 'ages_logo.png'
        )

    def _ages_apply_sheet_defaults(self, sheet):
        sheet.set_default_row(AGES_ROW_HEIGHT)

    def _ages_xlsx_body_font_size(self):
        return AGES_XLSX_BODY_FONT_SIZE

    def _ages_brand_formats(self, workbook):
        return {
            'brand_company': workbook.add_format({
                'bold': True,
                'font_size': 17,
                'font_color': AGES_COLOR_PRIMARY,
                'valign': 'vcenter',
            }),
            'brand_address': workbook.add_format({
                'font_size': 14,
                'font_color': '#5C4A4A',
                'valign': 'vcenter',
            }),
            'brand_email': workbook.add_format({
                'font_size': 14,
                'font_color': AGES_COLOR_EMAIL,
                'underline': True,
                'valign': 'vcenter',
            }),
            'brand_report_title': workbook.add_format({
                'bold': True,
                'font_size': 21,
                'font_color': '#FFFFFF',
                'bg_color': AGES_COLOR_PRIMARY,
                'align': 'left',
                'valign': 'vcenter',
            }),
            'brand_report_subtitle': workbook.add_format({
                'font_size': 13,
                'font_color': AGES_COLOR_SUBTITLE,
                'bg_color': AGES_COLOR_PRIMARY,
                'align': 'left',
                'valign': 'vcenter',
            }),
        }

    def _ages_write_pdf_header_rows(self, sheet, workbook, report_title, subtitle='', merge_col=7):
        """Write corporate header block; return next free row index."""
        brand = self._ages_brand_formats(workbook)
        self._ages_apply_sheet_defaults(sheet)

        sheet.set_row(0, 40)
        sheet.set_row(1, 26)
        sheet.set_row(2, 26)

        logo_path = self._ages_logo_path()
        if logo_path:
            sheet.set_column(0, 1, 16)
            sheet.insert_image(
                0, 0, logo_path,
                {'x_scale': 0.34, 'y_scale': 0.34, 'x_offset': 4, 'y_offset': 2},
            )

        sheet.merge_range(0, 2, 0, merge_col, AGES_COMPANY_NAME, brand['brand_company'])
        sheet.merge_range(1, 2, 1, merge_col, AGES_COMPANY_ADDRESS, brand['brand_address'])
        sheet.merge_range(2, 2, 2, merge_col, AGES_COMPANY_EMAIL, brand['brand_email'])

        row = 4
        sheet.merge_range(row, 0, row, merge_col, report_title, brand['brand_report_title'])
        sheet.set_row(row, 32)
        row += 1
        if subtitle:
            sheet.merge_range(row, 0, row, merge_col, subtitle, brand['brand_report_subtitle'])
            sheet.set_row(row, 24)
            row += 1
        return row + 1

# -*- coding: utf-8 -*-

from odoo import models

from .opal_report_engine import OpalVendorBalanceEngine
from .opal_report_report import TAB_TITLES
from ..models.opal_report_wizard import _options_from_wizard


class OpalVendorBalanceXlsx(models.AbstractModel):
    _name = 'report.ages_opal_vendor_balance.opal_vendor_balance_report_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'OPAL Vendor Balance Excel'

    def generate_xlsx_report(self, workbook, data, wizards):
        form = (data or {}).get('form') or {}
        if not form and wizards:
            form = _options_from_wizard(wizards[0])
        engine = OpalVendorBalanceEngine(self.env, form)
        report = engine.get_report_data()
        columns = engine.visible_columns(report['columns'])
        tab = report.get('tab') or 'vendor_project'
        title = 'OPAL Vendor Balance — %s' % TAB_TITLES.get(tab, tab)
        headers = [col['label'] for col in columns]
        sheet = workbook.add_worksheet(TAB_TITLES.get(tab, 'Report')[:31])
        sheet.set_landscape()
        widths = [18, 36, 18, 22, 28, 16, 16, 16]
        for index, width in enumerate(widths[:len(headers)]):
            sheet.set_column(index, index, width)

        header_fmt = workbook.add_format({
            'bold': True, 'font_size': 12, 'font_color': '#FFFFFF',
            'bg_color': '#8B1A1A', 'border': 1, 'align': 'center',
        })
        text_fmt = workbook.add_format({'font_size': 11, 'border': 1})
        bold_fmt = workbook.add_format({'bold': True, 'font_size': 11, 'border': 1})
        amount_fmt = workbook.add_format({
            'font_size': 11, 'num_format': '#,##0.00', 'border': 1, 'align': 'right',
        })
        amount_bold = workbook.add_format({
            'bold': True, 'font_size': 11, 'num_format': '#,##0.00',
            'border': 1, 'align': 'right',
        })

        row = self._ages_write_pdf_header_rows(
            sheet, workbook, title,
            'Reference only — OPAL static data. Does not post to Odoo ledgers.',
            merge_col=max(len(headers) - 1, 1),
        )
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_fmt)
        row += 1
        for line in report['lines']:
            is_overall = line.get('source') in ('odoo_overall', 'opal_overall', 'opal_vendor_total')
            text = bold_fmt if is_overall else text_fmt
            amount = amount_bold if is_overall else amount_fmt
            for col, column in enumerate(columns):
                key = column['id']
                value = line.get('source_label') if key == 'source' else line.get(key)
                if column.get('type') == 'monetary':
                    if value in (None, False, ''):
                        sheet.write(row, col, '', text)
                    else:
                        sheet.write_number(row, col, float(value or 0.0), amount)
                else:
                    if value in (None, False):
                        value = ''
                    sheet.write(row, col, value, text)
            row += 1
        totals = report.get('totals') or {}
        sheet.write(row, 0, 'OPAL total', bold_fmt)
        for col, column in enumerate(columns):
            if col == 0:
                continue
            if column.get('type') == 'monetary' and column['id'] in totals:
                sheet.write_number(row, col, float(totals[column['id']] or 0.0), amount_bold)
            else:
                sheet.write(row, col, '', bold_fmt)

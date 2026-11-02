# -*- coding: utf-8 -*-

from odoo import models

from .aged_partner_balance_engine import AgedPartnerBalanceEngine
from .report_branding import AGES_COLOR_PRIMARY, AGES_COLOR_SECTION


class AgedPartnerBalanceXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.aged_partner_balance_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Aged Receivable and Payable Excel Report'

    def _formats(self, workbook):
        border = '#EED6DA'
        return {
            'header': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'font_color': '#FFFFFF',
                'bg_color': AGES_COLOR_PRIMARY,
                'border': 1,
                'border_color': AGES_COLOR_PRIMARY,
                'align': 'center',
                'valign': 'vcenter',
            }),
            'header_left': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'font_color': '#FFFFFF',
                'bg_color': AGES_COLOR_PRIMARY,
                'border': 1,
                'border_color': AGES_COLOR_PRIMARY,
                'align': 'left',
                'valign': 'vcenter',
            }),
            'total': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'bg_color': '#EEF3F9',
                'border': 1,
                'border_color': border,
            }),
            'partner': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'font_color': AGES_COLOR_PRIMARY,
                'bg_color': AGES_COLOR_SECTION,
                'border': 1,
                'border_color': border,
            }),
            'detail': workbook.add_format({
                'font_size': 11,
                'border': 1,
                'border_color': border,
            }),
            'amount_total': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'bg_color': '#EEF3F9',
                'num_format': '#,##0.00;[Red]-#,##0.00',
                'border': 1,
                'border_color': border,
                'align': 'right',
            }),
            'amount_partner': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'font_color': AGES_COLOR_PRIMARY,
                'bg_color': AGES_COLOR_SECTION,
                'num_format': '#,##0.00;[Red]-#,##0.00',
                'border': 1,
                'border_color': border,
                'align': 'right',
            }),
            'amount_detail': workbook.add_format({
                'font_size': 11,
                'num_format': '#,##0.00;[Red]-#,##0.00',
                'border': 1,
                'border_color': border,
                'align': 'right',
            }),
        }

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            from ..models.aged_partner_balance_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])
        form = dict(form or {}, unfold_all=True)
        engine = AgedPartnerBalanceEngine(self.env, form)
        report_data = engine.get_report_data()
        lines = engine.flatten_lines(report_data['lines'])
        columns = report_data['columns']
        formats = self._formats(workbook)

        sheet = workbook.add_worksheet(report_data['title'][:31])
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.set_column(0, 0, 44)
        for index, column in enumerate(columns, start=1):
            width = 14
            if column['type'] == 'date':
                width = 13
            elif column['key'] == 'account_name':
                width = 34
            elif column['key'] == 'currency_name':
                width = 11
            sheet.set_column(index, index, width)

        basis_label = (
            'Invoice Date'
            if form.get('aging_based_on') == 'invoice'
            else 'Due Date'
        )
        subtitle = (
            f"As of {report_data['date_label']} · "
            f"Based on {basis_label} · "
            f"{engine.aging_interval} Day intervals · "
            f"Currency: {self.env.company.currency_id.name}"
        )
        last_column = len(columns)
        row = self._ages_write_pdf_header_rows(
            sheet,
            workbook,
            report_data['title'],
            subtitle,
            merge_col=last_column,
        )

        sheet.write(row, 0, 'Partner / Entry', formats['header_left'])
        for column_index, column in enumerate(columns, start=1):
            sheet.write(row, column_index, column['name'], formats['header'])
        header_row = row
        row += 1

        for line in lines:
            line_type = line['line_type']
            if line_type == 'total':
                text_format = formats['total']
                amount_format = formats['amount_total']
            elif line_type == 'partner':
                text_format = formats['partner']
                amount_format = formats['amount_partner']
            else:
                text_format = formats['detail']
                amount_format = formats['amount_detail']

            label = line['name']
            if line_type == 'move_line':
                label = f"  {line.get('communication') or line['name']}"
            sheet.write(row, 0, label, text_format)

            for column_index, column in enumerate(columns, start=1):
                value = line.get(column['key'])
                if column['type'] in ('monetary', 'amount_currency'):
                    if value not in (False, None, 0):
                        sheet.write_number(row, column_index, value, amount_format)
                    else:
                        sheet.write_blank(row, column_index, None, amount_format)
                else:
                    sheet.write(row, column_index, value or '', text_format)
            row += 1

        sheet.freeze_panes(header_row + 1, 1)
        if row > header_row + 1:
            sheet.autofilter(header_row, 0, row - 1, last_column)

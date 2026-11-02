# -*- coding: utf-8 -*-

from odoo import models

from .retention_report_engine import RetentionReportEngine


class RetentionReportXlsx(models.AbstractModel):
    _name = 'report.ages_project_reporting.retention_report_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Retention Report Excel'

    COLOR_NAVY = '#8B1A1A'
    COLOR_SECTION = '#FAF0F1'

    def _build_formats(self, workbook):
        return {
            'header': workbook.add_format({
                'bold': True, 'font_size': 12, 'font_color': '#FFFFFF',
                'bg_color': self.COLOR_NAVY, 'border': 1, 'align': 'center',
            }),
            'client': workbook.add_format({'bold': True, 'font_size': 12, 'border': 1}),
            'contract': workbook.add_format({'font_size': 12, 'border': 1, 'bg_color': '#F8F9FA'}),
            'detail': workbook.add_format({'font_size': 12, 'border': 1}),
            'total': workbook.add_format({
                'bold': True, 'font_size': 12, 'bg_color': self.COLOR_SECTION, 'border': 1,
            }),
            'amount': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.00', 'border': 1, 'align': 'right',
            }),
            'amount_bold': workbook.add_format({
                'bold': True, 'font_size': 12, 'num_format': '#,##0.00',
                'border': 1, 'align': 'right', 'bg_color': self.COLOR_SECTION,
            }),
            'amount_red': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.00', 'border': 1,
                'align': 'right', 'font_color': '#C0392B',
            }),
        }

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            from ..models.retention_report_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])
        form = dict(form, unfold_all=True)

        engine = RetentionReportEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(
            report_data['lines'],
            unfolded_ids=[line['id'] for line in report_data['lines'] if line.get('foldable')],
        )
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('Retention Report')
        sheet.set_landscape()
        headers = ['Client / Entry', 'Date', 'Account', 'Debit', 'Credit', 'Balance']
        widths = [48, 12, 28, 16, 16, 16]
        for idx, width in enumerate(widths):
            sheet.set_column(idx, idx, width)

        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Retention Report',
            f"Period: {report_data['date_label']}", merge_col=5,
        )

        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts['header'])
        row += 1

        for line in flat_lines:
            line_type = line.get('line_type')
            if line_type == 'total':
                text_fmt = fmts['total']
                amt_fmt = fmts['amount_bold']
            elif line_type == 'client':
                text_fmt = fmts['client']
                amt_fmt = fmts['amount']
            elif line_type == 'contract':
                text_fmt = fmts['contract']
                amt_fmt = fmts['amount']
            else:
                text_fmt = fmts['detail']
                amt_fmt = fmts['amount_red'] if (line.get('balance') or 0) < 0 else fmts['amount']

            indent = '  ' * (line.get('level') or 0)
            name = line.get('name') or ''
            if line.get('running_bill_name'):
                name = f"{name}  (from running bill {line['running_bill_name']})"
            sheet.write(row, 0, f"{indent}{name}", text_fmt)
            sheet.write(row, 1, line.get('date') or '', text_fmt)
            sheet.write(row, 2, line.get('account_name') or '', text_fmt)
            for col, key in enumerate(('debit', 'credit', 'balance'), start=3):
                value = line.get(key, 0.0) or 0.0
                if line_type == 'move_line' and key != 'balance' and not value:
                    sheet.write(row, col, '', text_fmt)
                else:
                    sheet.write_number(row, col, value, amt_fmt)
            row += 1

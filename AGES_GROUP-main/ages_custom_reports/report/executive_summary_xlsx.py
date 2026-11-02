from odoo import models

from .executive_summary_engine import ExecutiveSummaryEngine


class ExecutiveSummaryXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.executive_summary_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Executive Summary Excel Report'

    COLOR_NAVY = '#8B1A1A'
    COLOR_SECTION = '#FAF0F1'

    def _build_formats(self, workbook):
        return {
            'title': workbook.add_format({
                'bold': True, 'font_size': 17, 'font_color': self.COLOR_NAVY,
            }),
            'meta': workbook.add_format({
                'font_size': 12, 'font_color': '#5C4A4A', 'italic': True,
            }),
            'section': workbook.add_format({
                'bold': True, 'font_size': 12, 'bg_color': self.COLOR_SECTION,
                'border': 1, 'font_color': self.COLOR_NAVY,
            }),
            'metric': workbook.add_format({'font_size': 12, 'border': 1}),
            'amount': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.00', 'border': 1, 'align': 'right',
            }),
            'amount_red': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.00', 'border': 1,
                'align': 'right', 'font_color': '#C0392B',
            }),
            'pct': workbook.add_format({
                'font_size': 12, 'num_format': '0.0"%"', 'border': 1, 'align': 'right',
            }),
            'float_fmt': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.0', 'border': 1, 'align': 'right',
            }),
        }

    def _format_value(self, line, fmts):
        value = line.get('balance', 0.0)
        figure_type = line.get('figure_type', 'monetary')
        if line.get('line_type') == 'section':
            return '', fmts['section']
        if figure_type == 'percentage':
            return value, fmts['pct']
        if figure_type == 'float':
            fmt = fmts['amount_red'] if value < 0 else fmts['float_fmt']
            return value, fmt
        fmt = fmts['amount_red'] if value < 0 else fmts['amount']
        return value, fmt

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            from ..models.executive_summary_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])

        engine = ExecutiveSummaryEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('Executive Summary')
        sheet.set_column('A:A', 70)
        sheet.set_column('B:B', 18)

        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Executive Summary',
            f"Period: {report_data['date_label']}", merge_col=1,
        )

        for line in flat_lines:
            indent = '    ' if line['line_type'] == 'metric' else ''
            label = f"{indent}{line['name']}"
            if line['line_type'] == 'section':
                sheet.write(row, 0, label, fmts['section'])
                sheet.write(row, 1, '', fmts['section'])
            else:
                value, fmt = self._format_value(line, fmts)
                sheet.write(row, 0, label, fmts['metric'])
                if line.get('figure_type') == 'monetary':
                    sheet.write_number(row, 1, value, fmt)
                else:
                    sheet.write_number(row, 1, value, fmt)
            row += 1

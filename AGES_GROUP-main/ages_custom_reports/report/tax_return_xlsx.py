from odoo import models

from .tax_return_engine import TaxReturnEngine


class TaxReturnXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.tax_return_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Tax Return Excel Report'

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
            'header': workbook.add_format({
                'bold': True, 'font_size': 12, 'font_color': '#FFFFFF',
                'bg_color': self.COLOR_NAVY, 'border': 1, 'align': 'center',
            }),
            'section': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
                'bg_color': self.COLOR_SECTION,
            }),
            'tax': workbook.add_format({
                'font_size': 12, 'border': 1,
            }),
            'total': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
                'bg_color': self.COLOR_SECTION,
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
            'pct': workbook.add_format({
                'font_size': 12, 'num_format': '0.00"%"', 'border': 1, 'align': 'right',
            }),
        }

    def _write_amount(self, sheet, row, col, value, fmt, red_fmt, show=True):
        if not show or value is False:
            sheet.write(row, col, '', fmt)
            return
        sheet.write(row, col, value, red_fmt if value < 0 else fmt)

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            from ..models.tax_return_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])

        form = dict(form, unfold_all=True)
        engine = TaxReturnEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)
        comparison = report_data['comparison']

        sheet = workbook.add_worksheet('Tax Return')
        last_col = 6 if comparison else 2
        sheet.set_column('A:A', 52)
        sheet.set_column(1, last_col, 16)

        subtitle = (
            f"Period: {report_data['date_label']}  ·  "
            f"{report_data['report_name']}  ·  "
            f"Currency: {company.currency_id.name}"
        )
        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Tax Return', subtitle, merge_col=last_col,
        )

        if comparison:
            sheet.merge_range(row, 1, row, 2, report_data['period_label'], fmts['header'])
            sheet.merge_range(row, 3, row, 4, report_data['comparison_label'], fmts['header'])
            sheet.merge_range(row, 5, row, 6, '% Comparison', fmts['header'])
            row += 1
            headers = ['', 'base', 'Tax Amount', 'base', 'Tax Amount', 'base %', 'Tax %']
        else:
            sheet.merge_range(row, 1, row, 2, report_data['period_label'], fmts['header'])
            row += 1
            headers = ['', 'base', 'Tax Amount']

        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts['header'])
        row += 1

        for line in flat_lines:
            line_type = line['line_type']
            if line_type == 'section':
                text_fmt = fmts['section']
                amt_fmt = fmts['amount_bold']
            elif line_type == 'total':
                text_fmt = fmts['total']
                amt_fmt = fmts['amount_bold']
            else:
                text_fmt = fmts['tax']
                amt_fmt = fmts['amount']

            indent = '    ' * line['level']
            sheet.write(row, 0, f"{indent}{line['name']}", text_fmt)
            self._write_amount(
                sheet, row, 1, line['base'], amt_fmt, fmts['amount_red'],
                show=line.get('show_base'),
            )
            self._write_amount(
                sheet, row, 2, line['tax'], amt_fmt, fmts['amount_red'],
                show=line.get('show_tax'),
            )
            if comparison:
                self._write_amount(
                    sheet, row, 3, line['comp_base'], amt_fmt, fmts['amount_red'],
                    show=line.get('show_base'),
                )
                self._write_amount(
                    sheet, row, 4, line['comp_tax'], amt_fmt, fmts['amount_red'],
                    show=line.get('show_tax'),
                )
                self._write_amount(
                    sheet, row, 5, line['pct_base'], fmts['pct'], fmts['amount_red'],
                    show=line.get('show_base') and line['pct_base'] is not False,
                )
                self._write_amount(
                    sheet, row, 6, line['pct_tax'], fmts['pct'], fmts['amount_red'],
                    show=line.get('show_tax') and line['pct_tax'] is not False,
                )
            row += 1

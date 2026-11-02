from odoo import models

from .trial_balance_engine import TrialBalanceEngine


class TrialBalanceXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.trial_balance_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Trial Balance Excel Report'

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
            'group': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
            }),
            'subtotal': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
                'bg_color': self.COLOR_SECTION,
            }),
            'account': workbook.add_format({
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
        }

    def _write_amount(self, sheet, row, col, value, fmt, red_fmt):
        sheet.write(row, col, value, red_fmt if value < 0 else fmt)

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            from ..models.trial_balance_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])

        form = dict(form, unfold_all=True)
        engine = TrialBalanceEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('Trial Balance')
        sheet.set_landscape()
        sheet.set_column('A:A', 48)
        sheet.set_column('B:E', 16)

        subtitle = (
            f"Period: {report_data['date_label']}  ·  "
            f"Currency: {company.currency_id.name}"
        )
        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Trial Balance', subtitle, merge_col=4,
        )

        sheet.merge_range(row, 1, row, 1, 'Initial Balance', fmts['header'])
        sheet.merge_range(row, 2, row, 3, report_data['period_label'], fmts['header'])
        sheet.merge_range(row, 4, row, 4, 'End Balance', fmts['header'])
        row += 1

        headers = ['', 'Balance', 'Debit', 'Credit', 'Balance']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts['header'])
        row += 1

        for line in flat_lines:
            line_type = line['line_type']
            if line_type == 'total':
                text_fmt = fmts['total']
                amt_fmt = fmts['amount_bold']
            elif line_type in ('group', 'subtotal'):
                text_fmt = fmts['subtotal'] if line_type == 'subtotal' else fmts['group']
                amt_fmt = fmts['amount_bold']
            else:
                text_fmt = fmts['account']
                amt_fmt = fmts['amount']

            indent = '    ' * line['level']
            sheet.write(row, 0, f"{indent}{line['name']}", text_fmt)
            self._write_amount(
                sheet, row, 1, line['initial_balance'], amt_fmt, fmts['amount_red'],
            )
            self._write_amount(
                sheet, row, 2, line['period_debit'], amt_fmt, fmts['amount_red'],
            )
            self._write_amount(
                sheet, row, 3, line['period_credit'], amt_fmt, fmts['amount_red'],
            )
            self._write_amount(
                sheet, row, 4, line['end_balance'], amt_fmt, fmts['amount_red'],
            )
            row += 1

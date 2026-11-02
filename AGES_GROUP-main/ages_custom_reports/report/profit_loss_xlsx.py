from odoo import models, fields

from .profit_loss_engine import ProfitLossEngine


class ProfitLossXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.profit_loss_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Profit and Loss Excel Report'

    COLOR_NAVY = '#8B1A1A'
    COLOR_SECTION = '#FAF0F1'
    COLOR_BORDER = '#EED6DA'

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
                'bold': True, 'font_size': 12, 'bg_color': self.COLOR_SECTION,
                'border': 1, 'font_color': self.COLOR_NAVY,
            }),
            'group': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
            }),
            'account': workbook.add_format({
                'font_size': 12, 'border': 1,
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
            from ..models.profit_loss_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])

        engine = ProfitLossEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('Profit and Loss')
        sheet.set_landscape()
        sheet.set_column('A:A', 70)
        sheet.set_column('B:B', 18)

        subtitle = (
            f"Period: {report_data['date_label']}  ·  "
            f"Currency: {company.currency_id.name}"
        )
        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Profit and Loss', subtitle, merge_col=1,
        )

        sheet.write(row, 0, '', fmts['header'])
        sheet.write(row, 1, f"Balance\n{report_data['date_label']}", fmts['header'])
        row += 1

        for line in flat_lines:
            indent = '    ' * line['level']
            label = f"{indent}{line['name']}"
            balance = line['balance']
            if line['line_type'] in ('section', 'total'):
                text_fmt = fmts['section']
                amt_fmt = fmts['amount_bold']
            elif line['line_type'] == 'account':
                text_fmt = fmts['account']
                amt_fmt = fmts['amount_red'] if balance < 0 else fmts['amount']
            else:
                text_fmt = fmts['group']
                amt_fmt = fmts['amount_red'] if balance < 0 else fmts['amount']

            sheet.write(row, 0, label, text_fmt)
            sheet.write_number(row, 1, balance, amt_fmt)
            row += 1

from odoo import models

from .general_ledger_engine import GeneralLedgerEngine


class GeneralLedgerXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.general_ledger_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'General Ledger Excel Report'

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
            'account': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
            }),
            'detail': workbook.add_format({
                'font_size': 12, 'border': 1,
            }),
            'total': workbook.add_format({
                'bold': True, 'font_size': 12, 'border': 1,
                'bg_color': self.COLOR_SECTION,
            }),
            'text': workbook.add_format({
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
            from ..models.general_ledger_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])

        form = dict(form, unfold_all=True)
        engine = GeneralLedgerEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('General Ledger')
        sheet.set_landscape()
        sheet.set_column('A:A', 12)
        sheet.set_column('B:B', 48)
        sheet.set_column('C:C', 32)
        sheet.set_column('D:D', 14)
        sheet.set_column('E:G', 14)

        subtitle = (
            f"Period: {report_data['date_label']}  ·  "
            f"Currency: {company.currency_id.name}"
        )
        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'General Ledger', subtitle, merge_col=6,
        )

        headers = ['Date', 'Communication', 'Partner', 'Currency', 'Debit', 'Credit', 'Balance']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts['header'])
        row += 1

        for line in flat_lines:
            indent = '    ' * line['level']
            if line['line_type'] == 'total':
                text_fmt = fmts['total']
                amt_fmt = fmts['amount_bold']
            elif line['line_type'] == 'account':
                text_fmt = fmts['account']
                amt_fmt = fmts['amount_red'] if line['balance'] < 0 else fmts['amount']
            else:
                text_fmt = fmts['detail']
                amt_fmt = fmts['amount_red'] if line['balance'] < 0 else fmts['amount']

            label = f"{indent}{line['name']}"
            sheet.write(row, 0, line.get('date') or '', text_fmt if line['line_type'] == 'account' else fmts['text'])
            sheet.write(row, 1, label if line['line_type'] == 'account' else (line.get('communication') or label), text_fmt if line['line_type'] in ('account', 'total') else fmts['text'])
            sheet.write(row, 2, line.get('partner_name') or '', fmts['text'])
            currency_display = ''
            if line.get('amount_currency') and line.get('currency_name'):
                currency_display = f"{line['amount_currency']:,.2f} {line['currency_name']}"
            sheet.write(row, 3, currency_display, fmts['text'])
            sheet.write_number(row, 4, line['debit'] or 0.0, amt_fmt)
            sheet.write_number(row, 5, line['credit'] or 0.0, amt_fmt)
            sheet.write_number(row, 6, line['balance'] or 0.0, amt_fmt)
            row += 1

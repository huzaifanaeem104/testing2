from odoo import models

from .journal_audit_engine import JournalAuditEngine


class JournalAuditXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.journal_audit_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Journal Audit Excel Report'

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
                'bold': True, 'font_size': 12, 'bg_color': self.COLOR_SECTION, 'border': 1,
            }),
            'journal': workbook.add_format({'bold': True, 'font_size': 12, 'border': 1}),
            'detail': workbook.add_format({'font_size': 12, 'border': 1}),
            'amount': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.00', 'border': 1, 'align': 'right',
            }),
            'amount_red': workbook.add_format({
                'font_size': 12, 'num_format': '#,##0.00', 'border': 1,
                'align': 'right', 'font_color': '#C0392B',
            }),
        }

    def _write_main_table(self, sheet, row, flat_lines, fmts):
        headers = ['Name', 'Code', 'Debit', 'Credit', 'Balance']
        widths = [52, 14, 14, 14, 14]
        for idx, width in enumerate(widths):
            sheet.set_column(idx, idx, width)

        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts['header'])
        row += 1

        for line in flat_lines:
            if line['line_type'] == 'journal':
                text_fmt = fmts['journal']
            else:
                text_fmt = fmts['detail']
            amt_fmt = fmts['amount']
            balance = line.get('balance')
            if balance not in (False, None) and balance < 0:
                amt_fmt = fmts['amount_red']

            label = line['name']
            if line['line_type'] == 'account':
                label = f"  {label}"

            sheet.write(row, 0, label, text_fmt)
            sheet.write(row, 1, line.get('code') or '', text_fmt)
            if line.get('debit'):
                sheet.write_number(row, 2, line['debit'], fmts['amount'])
            else:
                sheet.write(row, 2, '', text_fmt)
            if line.get('credit'):
                sheet.write_number(row, 3, line['credit'], fmts['amount'])
            else:
                sheet.write(row, 3, '', text_fmt)
            if balance not in (False, None):
                sheet.write_number(row, 4, balance, amt_fmt)
            else:
                sheet.write(row, 4, '', text_fmt)
            row += 1
        return row + 1

    def _write_tax_summary(self, sheet, row, tax_summary, fmts):
        if not tax_summary:
            return row

        sheet.write(row, 0, 'Global Tax Summary', fmts['section'])
        sheet.merge_range(row, 0, row, 4, 'Global Tax Summary', fmts['section'])
        row += 2

        taxes = tax_summary.get('taxes_applied') or []
        if taxes:
            sheet.write(row, 0, 'Taxes Applied', fmts['section'])
            row += 1
            headers = ['Name', 'Base Amount', 'Tax Amount', 'Non-Deductible']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, fmts['header'])
            row += 1
            for tax in taxes:
                sheet.write(row, 0, tax['name'], fmts['detail'])
                sheet.write_number(row, 1, tax.get('base_amount', 0.0), fmts['amount'])
                sheet.write_number(row, 2, tax.get('tax_amount', 0.0), fmts['amount'])
                sheet.write_number(row, 3, tax.get('non_deductible', 0.0), fmts['amount'])
                row += 1
            row += 1

        grids = tax_summary.get('tax_grids') or []
        if grids:
            sheet.write(row, 0, 'Impacted Tax Grids', fmts['section'])
            row += 1
            headers = ['Grid', '+', '-', 'Impact On Grid']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, fmts['header'])
            row += 1
            for grid in grids:
                sheet.write(row, 0, grid['name'], fmts['detail'])
                if grid.get('plus'):
                    sheet.write_number(row, 1, grid['plus'], fmts['amount'])
                else:
                    sheet.write(row, 1, '', fmts['detail'])
                if grid.get('minus'):
                    sheet.write_number(row, 2, grid['minus'], fmts['amount'])
                else:
                    sheet.write(row, 2, '', fmts['detail'])
                sheet.write_number(row, 3, grid.get('impact', 0.0), fmts['amount'])
                row += 1
        return row

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            from ..models.journal_audit_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])
        form = dict(form, unfold_all=True)

        engine = JournalAuditEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('Journal Audit')
        sheet.set_landscape()

        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Journal Audit',
            f"Period: {report_data['date_label']}", merge_col=4,
        )

        row = self._write_main_table(sheet, row, flat_lines, fmts)
        self._write_tax_summary(sheet, row, report_data.get('tax_summary'), fmts)

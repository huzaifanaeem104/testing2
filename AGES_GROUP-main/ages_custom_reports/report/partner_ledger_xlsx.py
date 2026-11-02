from odoo import models

from .partner_ledger_engine import PartnerLedgerEngine


class PartnerLedgerXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.partner_ledger_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Partner Ledger Excel Report'

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
            'partner': workbook.add_format({'bold': True, 'font_size': 12, 'border': 1}),
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
            from ..models.partner_ledger_wizard import _options_from_wizard
            form = _options_from_wizard(wizards[0])
        form = dict(form, unfold_all=True)

        engine = PartnerLedgerEngine(self.env, form)
        report_data = engine.get_report_data()
        flat_lines = engine.flatten_lines(report_data['lines'])
        company = self.env.company
        fmts = self._build_formats(workbook)

        sheet = workbook.add_worksheet('Partner Ledger')
        sheet.set_landscape()
        headers = [
            'Partner / Entry', 'Journal', 'Account', 'Project', 'Date', 'Due Date',
            'Matching', 'Debit', 'Credit', 'Balance',
        ]
        widths = [48, 12, 16, 28, 12, 12, 14, 14, 14, 14]
        for idx, width in enumerate(widths):
            sheet.set_column(idx, idx, width)

        project_id = form.get('analytic_account_id')
        project_label = 'All Projects'
        if project_id:
            project = self.env['account.analytic.account'].browse(project_id)
            from .report_display import clip_project_name
            project_label = clip_project_name(project.name or project.display_name) or project_label

        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Partner Ledger',
            f"Period: {report_data['date_label']}  |  Project: {project_label}",
            merge_col=9,
        )

        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts['header'])
        row += 1

        for line in flat_lines:
            if line['line_type'] == 'total':
                text_fmt = fmts['total']
                amt_fmt = fmts['amount_bold']
            elif line['line_type'] == 'partner':
                text_fmt = fmts['partner']
                amt_fmt = fmts['amount']
            else:
                text_fmt = fmts['detail']
                amt_fmt = fmts['amount_red'] if line.get('balance', 0) < 0 else fmts['amount']

            label = line['name']
            if line['line_type'] in ('initial', 'move_line'):
                label = f"  {line.get('communication') or line['name']}"
            if line.get('badge'):
                label = f"{label}  [{line['badge']}]"

            sheet.write(row, 0, label, text_fmt)
            sheet.write(row, 1, line.get('journal_code') or '', text_fmt)
            sheet.write(row, 2, line.get('account_code') or '', text_fmt)
            sheet.write(row, 3, line.get('analytic_name') or '', text_fmt)
            sheet.write(row, 4, line.get('date') or '', text_fmt)
            sheet.write(row, 5, line.get('due_date') or '', text_fmt)
            sheet.write(row, 6, line.get('matching_number') or '', text_fmt)
            if line.get('debit'):
                sheet.write_number(row, 7, line['debit'], amt_fmt)
            else:
                sheet.write(row, 7, '', text_fmt)
            if line.get('credit'):
                sheet.write_number(row, 8, line['credit'], amt_fmt)
            else:
                sheet.write(row, 8, '', text_fmt)
            sheet.write_number(row, 9, line.get('balance', 0.0), amt_fmt)
            row += 1

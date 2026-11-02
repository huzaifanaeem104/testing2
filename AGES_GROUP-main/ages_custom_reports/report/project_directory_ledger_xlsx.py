from odoo import models, fields

from .project_directory_ledger_common import (
    apply_account_payable_visibility,
    apply_bank_visibility,
    apply_cost_of_revenue_visibility,
    apply_target_move_domain,
    build_filter_labels,
    compute_grand_totals,
    compute_group_running_balances,
    get_group_by_label,
    resolve_line_project,
)


class ProjectDirectoryLedgerXlsx(models.AbstractModel):
    _name = 'report.ages_custom_reports.project_dir_ledger_xlsx'
    _inherit = ['report.report_xlsx.abstract', 'report.ages_custom_reports.xlsx.mixin']
    _description = 'Project Directory Ledger Excel Report'

    # Brand palette
    COLOR_NAVY = '#8B1A1A'
    COLOR_BLUE = '#B22234'
    COLOR_HEADER_BG = '#8B1A1A'
    COLOR_GROUP_BG = '#FAF0F1'
    COLOR_SUBTOTAL_BG = '#FAF0F1'
    COLOR_ALT_ROW = '#F8FAFC'
    COLOR_BORDER = '#EED6DA'

    def _get_line_project(self, line, cache):
        return resolve_line_project(line, cache)

    def _build_formats(self, workbook):
        return {
            'company': workbook.add_format({
                'bold': True,
                'font_size': 18,
                'font_color': self.COLOR_NAVY,
                'align': 'left',
                'valign': 'vcenter',
            }),
            'title': workbook.add_format({
                'bold': True,
                'font_size': 16,
                'font_color': self.COLOR_BLUE,
                'align': 'left',
            }),
            'subtitle': workbook.add_format({
                'font_size': 13,
                'font_color': '#5C4A4A',
                'italic': True,
            }),
            'filter_label': workbook.add_format({
                'bold': True,
                'font_size': 13,
                'font_color': '#5C4A4A',
                'bg_color': '#F8FAFC',
                'border': 1,
                'border_color': self.COLOR_BORDER,
            }),
            'filter_value': workbook.add_format({
                'font_size': 14,
                'font_color': '#1A2332',
                'border': 1,
                'border_color': self.COLOR_BORDER,
            }),
            'summary_label': workbook.add_format({
                'bold': True,
                'font_size': 13,
                'font_color': '#5C4A4A',
                'align': 'center',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'bg_color': '#F8FAFC',
            }),
            'summary_value': workbook.add_format({
                'bold': True,
                'font_size': 17,
                'font_color': self.COLOR_NAVY,
                'align': 'center',
                'border': 1,
                'border_color': self.COLOR_BORDER,
            }),
            'header': workbook.add_format({
                'bold': True,
                'font_size': 12,
                'font_color': '#FFFFFF',
                'bg_color': self.COLOR_HEADER_BG,
                'border': 1,
                'border_color': self.COLOR_HEADER_BG,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
            }),
            'group_header': workbook.add_format({
                'bold': True,
                'font_size': 15,
                'font_color': self.COLOR_NAVY,
                'bg_color': self.COLOR_GROUP_BG,
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'left': 5,
                'left_color': self.COLOR_BLUE,
            }),
            'text': workbook.add_format({
                'font_size': 12,
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'valign': 'vcenter',
                'text_wrap': True,
            }),
            'text_alt': workbook.add_format({
                'font_size': 12,
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'bg_color': self.COLOR_ALT_ROW,
                'valign': 'vcenter',
                'text_wrap': True,
            }),
            'date': workbook.add_format({
                'font_size': 12,
                'num_format': 'yyyy-mm-dd',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'valign': 'vcenter',
            }),
            'date_alt': workbook.add_format({
                'font_size': 12,
                'num_format': 'yyyy-mm-dd',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'bg_color': self.COLOR_ALT_ROW,
                'valign': 'vcenter',
            }),
            'amount': workbook.add_format({
                'font_size': 12,
                'num_format': '#,##0.00',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'align': 'right',
                'valign': 'vcenter',
            }),
            'amount_alt': workbook.add_format({
                'font_size': 12,
                'num_format': '#,##0.00',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'bg_color': self.COLOR_ALT_ROW,
                'align': 'right',
                'valign': 'vcenter',
            }),
            'subtotal_label': workbook.add_format({
                'bold': True,
                'font_size': 12,
                'font_color': self.COLOR_NAVY,
                'bg_color': self.COLOR_SUBTOTAL_BG,
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'align': 'right',
                'valign': 'vcenter',
            }),
            'subtotal_amount': workbook.add_format({
                'bold': True,
                'font_size': 12,
                'font_color': self.COLOR_NAVY,
                'num_format': '#,##0.00',
                'bg_color': self.COLOR_SUBTOTAL_BG,
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'align': 'right',
                'valign': 'vcenter',
                'top': 2,
                'top_color': self.COLOR_BLUE,
            }),
            'grand_header': workbook.add_format({
                'bold': True,
                'font_size': 15,
                'font_color': '#FFFFFF',
                'bg_color': self.COLOR_NAVY,
                'align': 'center',
                'valign': 'vcenter',
            }),
            'grand_label': workbook.add_format({
                'bold': True,
                'font_size': 13,
                'font_color': '#5C4A4A',
                'bg_color': '#FFFFFF',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'align': 'center',
                'valign': 'vcenter',
            }),
            'grand_value': workbook.add_format({
                'bold': True,
                'font_size': 17,
                'font_color': self.COLOR_NAVY,
                'num_format': '#,##0.00',
                'bg_color': '#FFFFFF',
                'border': 1,
                'border_color': self.COLOR_BORDER,
                'align': 'center',
                'valign': 'vcenter',
            }),
        }

    def generate_xlsx_report(self, workbook, data, wizards):
        form = data.get('form', {})
        if not form and wizards:
            wizard = wizards[0]
            form = {
                'date_from': wizard.date_from,
                'date_to': wizard.date_to,
                'analytic_account_id': wizard.analytic_account_id.id,
                'account_id': wizard.account_id.id,
                'partner_id': wizard.partner_id.id,
                'hide_account_payable': wizard.hide_account_payable,
                'hide_cost_of_revenue': wizard.hide_cost_of_revenue,
                'hide_bank': wizard.hide_bank,
                'target_move': wizard.target_move,
            }
        company = self.env.company
        fmts = self._build_formats(workbook)

        domain = [('display_type', 'not in', ('line_section', 'line_note'))]
        if form.get('date_from'):
            domain.append(('date', '>=', form['date_from']))
        if form.get('date_to'):
            domain.append(('date', '<=', form['date_to']))
        if form.get('account_id'):
            domain.append(('account_id', '=', form['account_id']))
        if form.get('partner_id'):
            domain.append(('partner_id', '=', form['partner_id']))
        apply_target_move_domain(domain, form)

        move_lines = self.env['account.move.line'].search(domain, order='date asc, id asc')

        cache = {}
        target_aa_id = form.get('analytic_account_id')

        if target_aa_id:
            filtered_lines = []
            for line in move_lines:
                aa = self._get_line_project(line, cache)
                if aa and aa.id == target_aa_id:
                    filtered_lines.append(line)
            move_lines = filtered_lines

        move_lines = apply_account_payable_visibility(move_lines, form)
        move_lines = apply_cost_of_revenue_visibility(move_lines, form)
        move_lines = apply_bank_visibility(move_lines, form)

        partner_id = form.get('partner_id')
        if partner_id and not target_aa_id:
            group_by = 'analytic_distribution'
        elif target_aa_id and not partner_id:
            group_by = 'partner_id'
        else:
            group_by = 'analytic_distribution'

        grouped_data = {}
        for line in move_lines:
            if group_by == 'analytic_distribution':
                aa = self._get_line_project(line, cache)
                key_name = aa.name if aa else 'Uncategorized'
            else:
                key_name = line.partner_id.name if line.partner_id else 'No Partner'

            grouped_data.setdefault(key_name, []).append(line)

        running_balances = compute_group_running_balances(grouped_data)
        filter_labels = build_filter_labels(self.env, form)
        group_by_label = get_group_by_label(group_by)
        show_analytic_col = group_by != 'analytic_distribution'
        grand_totals = compute_grand_totals(grouped_data)
        report_date = fields.Date.context_today(self)

        sheet = workbook.add_worksheet('Project Directory Ledger')
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.set_margins(0.4, 0.4, 0.5, 0.5)

        headers = ['Date', 'Journal Entry', 'Partner', 'Label', 'Account']
        if show_analytic_col:
            headers.append('Analytic')
        headers.extend(['Debit', 'Credit', 'Balance'])
        col_count = len(headers)
        last_col = col_count - 1

        sheet.set_column('A:A', 12)
        sheet.set_column('B:B', 22)
        sheet.set_column('C:C', 32)
        sheet.set_column('D:D', 36)
        sheet.set_column('E:E', 40)
        if show_analytic_col:
            sheet.set_column('F:F', 28)
            sheet.set_column('G:I', 14)
        else:
            sheet.set_column('F:H', 14)

        subtitle = (
            f"{group_by_label} · Generated {report_date} · "
            f"Currency: {company.currency_id.name}"
        )
        row = self._ages_write_pdf_header_rows(
            sheet, workbook, 'Project Directory Ledger', subtitle, merge_col=last_col,
        )

        for label, value in filter_labels:
            sheet.write(row, 0, label, fmts['filter_label'])
            sheet.merge_range(row, 1, row, last_col, value, fmts['filter_value'])
            row += 1
        sheet.write(row, 0, 'Grouped By', fmts['filter_label'])
        sheet.merge_range(row, 1, row, last_col, group_by_label, fmts['filter_value'])
        row += 2

        sheet.write(row, 0, 'Total Groups', fmts['summary_label'])
        sheet.write(row, 1, 'Total Lines', fmts['summary_label'])
        sheet.write(row, 2, 'Currency', fmts['summary_label'])
        sheet.write(row + 1, 0, len(grouped_data), fmts['summary_value'])
        sheet.write(row + 1, 1, len(move_lines), fmts['summary_value'])
        sheet.write(row + 1, 2, company.currency_id.name, fmts['summary_value'])
        row += 3

        header_row = row
        for col, head in enumerate(headers):
            sheet.write(row, col, head, fmts['header'])
        sheet.autofilter(header_row, 0, header_row, last_col)
        row += 1

        for group, lines in grouped_data.items():
            sheet.merge_range(
                row, 0, row, last_col,
                f'{group_by_label}: {group}  ({len(lines)} lines)',
                fmts['group_header'],
            )
            row += 1

            total_credit = total_debit = total_balance = 0.0
            for idx, line in enumerate(lines):
                aa = self._get_line_project(line, cache)
                analytic_str = aa.name if aa else ''
                alt = idx % 2 == 1
                text_fmt = fmts['text_alt'] if alt else fmts['text']
                date_fmt = fmts['date_alt'] if alt else fmts['date']
                amount_fmt = fmts['amount_alt'] if alt else fmts['amount']
                col = 0

                if line.date:
                    sheet.write(row, col, fields.Date.to_string(line.date), date_fmt)
                else:
                    sheet.write(row, col, '', text_fmt)
                col += 1
                sheet.write(row, col, line.move_id.name or '', text_fmt)
                col += 1
                sheet.write(row, col, line.partner_id.name or '', text_fmt)
                col += 1
                sheet.write(row, col, line.name or '', text_fmt)
                col += 1
                sheet.write(
                    row, col,
                    line.account_id.display_name if line.account_id else '',
                    text_fmt,
                )
                col += 1
                if show_analytic_col:
                    sheet.write(row, col, analytic_str, text_fmt)
                    col += 1
                sheet.write_number(row, col, line.debit, amount_fmt)
                col += 1
                sheet.write_number(row, col, line.credit, amount_fmt)
                col += 1
                sheet.write_number(row, col, running_balances.get(line.id, line.balance), amount_fmt)

                total_credit += line.credit
                total_debit += line.debit
                total_balance += line.balance
                row += 1

            subtotal_colspan = 5 if show_analytic_col else 4
            sheet.merge_range(row, 0, row, subtotal_colspan, 'Subtotal', fmts['subtotal_label'])
            debit_col = subtotal_colspan + 1
            sheet.write_number(row, debit_col, total_debit, fmts['subtotal_amount'])
            sheet.write_number(row, debit_col + 1, total_credit, fmts['subtotal_amount'])
            sheet.write_number(row, debit_col + 2, total_balance, fmts['subtotal_amount'])
            row += 1

        if grouped_data:
            sheet.merge_range(row, 0, row, last_col, 'REPORT GRAND TOTAL', fmts['grand_header'])
            row += 1
            grand_cols = last_col + 1
            third = max(grand_cols // 3, 1)
            sheet.merge_range(row, 0, row, third - 1, 'Total Debit', fmts['grand_label'])
            sheet.merge_range(row, third, row, 2 * third - 1, 'Total Credit', fmts['grand_label'])
            sheet.merge_range(row, 2 * third, row, last_col, 'Net Balance', fmts['grand_label'])
            row += 1
            sheet.merge_range(row, 0, row, third - 1, grand_totals['debit'], fmts['grand_value'])
            sheet.merge_range(row, third, row, 2 * third - 1, grand_totals['credit'], fmts['grand_value'])
            sheet.merge_range(row, 2 * third, row, last_col, grand_totals['balance'], fmts['grand_value'])

from odoo import models, fields, api
from datetime import datetime


class StockValuationXlsx(models.AbstractModel):
    _name = 'report.stock_valuation.report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Stock Valuation Report with Category Totals'

    def generate_xlsx_report(self, workbook, data, objs):

        def safe(v):
            return 0 if v is None else v

        # 1. Parameters
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        product_id = data.get('product_id')  # Selected single product
        project_id = data.get('project_id')

        product = self.env['product.product'].browse(product_id)
        category = product.categ_id  # Fetching the category of the selected product

        # 2. Formatting
        title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        info_fmt = workbook.add_format({'bold': True})
        header_fmt = workbook.add_format(
            {'bold': True, 'bg_color': '#4F81BD', 'color': 'white', 'border': 1, 'align': 'center'})
        opening_cell_fmt = workbook.add_format(
            {'bold': True, 'bg_color': '#FFFF00', 'border': 1, 'num_format': '#,##0.00'})
        cell_fmt = workbook.add_format({'border': 1})
        in_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00', 'font_color': 'green'})
        out_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00', 'font_color': 'red'})
        num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        footer_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1, 'num_format': '#,##0.00'})

        sheet = workbook.add_worksheet('Valuation')
        sheet.set_column('A:I', 18)

        # 3. Header & Opening Qty
        sheet.merge_range('A1:I1', 'Stock Valuation Report', title_fmt)
        sheet.write('A3', 'Product:', info_fmt)
        sheet.write('B3', product.display_name)
        sheet.write('A4', 'Category:', info_fmt)
        sheet.write('B4', category.name)

        opening_qty = product.with_context(to_date=from_date).qty_available if from_date else 0.0
        sheet.write('G3', 'Opening Quantity:', info_fmt)
        sheet.write('H3', opening_qty, opening_cell_fmt)

        # 4. Table Headers
        row = 6
        headers = ['Date', 'Reference', 'From', 'To', 'In Qty', 'Out Qty', 'Balance', 'Total Value', 'Unit Cost']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_fmt)
        row += 1

        # 5. Data Fetching
        domain = [('product_id', '=', product.id), ('state', '=', 'done')]
        if from_date: domain.append(('date', '>=', from_date))
        if to_date: domain.append(('date', '<=', to_date))
        if project_id: domain.append(('project_id', '=', project_id))

        move_lines = self.env['stock.move.line'].search(domain, order='date asc')

        # 6. Data Loop
        running_balance = opening_qty
        total_in = 0.0
        total_out = 0.0

        for line in move_lines:
            qty = safe(line.quantity)
            in_q, out_q = 0.0, 0.0

            if line.location_dest_id.usage == 'internal': in_q = qty
            if line.location_id.usage == 'internal': out_q = qty

            running_balance += (in_q - out_q)
            total_in += in_q
            total_out += out_q

            unit_cost = product.standard_price
            val = running_balance * unit_cost

            sheet.write(row, 0, str(line.date.date()), cell_fmt)
            sheet.write(row, 1, line.reference or '', cell_fmt)
            sheet.write(row, 2, line.location_id.name, cell_fmt)
            sheet.write(row, 3, line.location_dest_id.name, cell_fmt)
            sheet.write(row, 4, in_q, in_fmt)
            sheet.write(row, 5, out_q, out_fmt)
            sheet.write(row, 6, running_balance, num_fmt)
            sheet.write(row, 7, val, num_fmt)
            sheet.write(row, 8, unit_cost, num_fmt)
            row += 1

        # ---------------------------------------------------------
        # 7. CATEGORY FOOTER (Sum, Total Value, Average Rate)
        # ---------------------------------------------------------
        row += 1
        sheet.merge_range(row, 0, row, 3, f'Total for Category: {category.name}', footer_fmt)

        # Total Qty Sum (Full Net Quantity)
        full_qty_sum = running_balance
        # Total Value (Net Balance * Cost)
        total_category_value = full_qty_sum * product.standard_price
        # Average Rate (Total Value / Total Quantity)
        avg_rate = product.standard_price  # Since we use standard price, avg matches unit cost

        sheet.write(row, 4, total_in, footer_fmt)
        sheet.write(row, 5, total_out, footer_fmt)
        sheet.write(row, 6, full_qty_sum, footer_fmt)  # Quantity Sum
        sheet.write(row, 7, total_category_value, footer_fmt)  # Total Value
        sheet.write(row, 8, avg_rate, footer_fmt)  # Average Rate

        return

    
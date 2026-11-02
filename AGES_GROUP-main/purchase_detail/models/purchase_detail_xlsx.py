# from odoo import models
# from datetime import datetime
#
#
# class OtpGenerateXlsx(models.AbstractModel):
#     _name = 'report.purchase_detail.report_xlsx'
#     _inherit = 'report.report_xlsx.abstract'
#     _description = 'Purchase Detail Report'
#
#     def generate_xlsx_report(self, workbook, data, objs):
#
#         def safe(v):
#             return 0 if v is None else v
#
#         from_date = data.get('from_date')
#         to_date = data.get('to_date')
#         supplier_id = data.get('supplier_id')
#
#         # Fetch supplier names (FIXED: correct model + safe handling)
#         suppliers = ''
#         if supplier_id:
#             supplier_records = self.env['res.partner'].search([('id', 'in', supplier_id)])
#             suppliers = ', '.join(supplier_records.mapped('name'))
#
#         domain = [('journal_id','=',10),('state','=','posted')]
#
#         if from_date:
#             domain.append(('invoice_date', '>=', from_date))
#
#         if to_date:
#             domain.append(('invoice_date', '<=', to_date))
#
#         if supplier_id:
#             domain.append(('partner_id', 'in', supplier_id))  # FIXED: 'in' instead of '='
#
#
#         recs = self.env['account.move'].search(domain)
#
#         sheet = workbook.add_worksheet('Purchase Detail')
#         sheet.set_column('A:N', 15)
#
#         # Formats
#         title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
#         info_fmt = workbook.add_format({'bold': True})
#         header_fmt = workbook.add_format({
#             'bold': True,
#             'bg_color': '#4F81BD',
#             'color': 'white',
#             'border': 1,
#             'align': 'center'
#         })
#         cell_fmt = workbook.add_format({'border': 1})
#         number_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
#         date_fmt = workbook.add_format({'border': 1, 'num_format': 'dd-mm-yyyy'})
#
#         # Hyperlink format
#         link_fmt = workbook.add_format({
#             'font_color': 'blue',
#             'underline': 1,
#             'border': 1
#         })
#
#         # Title & Filters
#         sheet.merge_range('A1:I1', 'Purchase Detail Report', title_fmt)
#
#         sheet.write('A3', 'From Date:', info_fmt)
#         sheet.write('B3', from_date or '')
#
#         sheet.write('A4', 'To Date:', info_fmt)
#         sheet.write('B4', to_date or '')
#
#         sheet.write('A5', 'Suppliers:', info_fmt)
#         sheet.write('B5', suppliers, info_fmt)
#
#         # Headers
#         row = 6
#         headers = [
#             'SR#', 'Date', 'Supplier',
#             'Bill No.', 'Bill Reference No.', 'Product/Account',
#             'Quantity', 'Rate', 'Amount'
#         ]
#
#         for col, header in enumerate(headers):
#             sheet.write(row, col, header, header_fmt)
#
#         # Data
#         sr_no = 1
#
#         for rec in recs:
#             invoice_date = rec.invoice_date
#             supplier = rec.partner_id.name or ''
#             bill_no = rec.id
#             inv_no = rec.name or ''
#
#             for line in rec.line_ids.filtered(lambda l: l.display_type == 'product'):
#                 product = line.product_id.name or ''
#                 quantity = line.quantity or 0
#                 rate = line.price_unit or 0
#                 amount = quantity * rate
#
#                 row += 1
#
#                 # Correct Odoo form view URL (WORKING)
#                 url = f"http://91.99.161.26/odoo/customer-invoices/{bill_no}"
#
#                 # Write data
#                 sheet.write(row, 0, sr_no, cell_fmt)
#                 sheet.write(row, 1, invoice_date, date_fmt)
#                 sheet.write(row, 2, supplier, cell_fmt)
#                 sheet.write(row, 3, bill_no, cell_fmt)
#
#                 # 🔥 Clickable Invoice Link
#                 sheet.write_url(row, 4, url, link_fmt, string=inv_no)
#
#                 sheet.write(row, 5, product, cell_fmt)
#                 sheet.write(row, 6, quantity, number_fmt)
#                 sheet.write(row, 7, rate, number_fmt)
#                 sheet.write(row, 8, amount, number_fmt)
#
#                 sr_no += 1
#
#         return
#
#
#
#
#
#
#
from odoo import models

from odoo.addons.purchase_detail.utils.xlsx_header import write_awt_excel_header


class OtpGenerateXlsx(models.AbstractModel):
    _name = 'report.purchase_detail.report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Purchase Detail Report'

    def generate_xlsx_report(self, workbook, data, objs):

        from_date = data.get('from_date')
        to_date = data.get('to_date')
        supplier_ids = data.get('supplier_id') or []

        project_ids = data.get('project_ids') or []
        uom_id = data.get('uom_id')
        city_location_ids = data.get('city_location_ids') or []

        # -----------------------------
        # Convert readable names
        suppliers = self.env['res.partner'].browse(supplier_ids).mapped('name')
        projects = self.env['account.analytic.account'].browse(project_ids).mapped('name')
        uom = self.env['uom.uom'].browse(uom_id).name if uom_id else ''
        cities = self.env['city.location'].browse(city_location_ids).mapped('name')

        # -----------------------------
        # DOMAIN
        domain = [
            ('journal_id', '=', 10),
            ('state', '=', 'posted')
        ]

        if from_date:
            domain.append(('invoice_date', '>=', from_date))

        if to_date:
            domain.append(('invoice_date', '<=', to_date))

        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))

        moves = self.env['account.move'].search(domain)

        # -----------------------------
        # SHEET
        sheet = workbook.add_worksheet('Purchase Detail')
        sheet.set_column('A:N', 18)

        label_fmt = workbook.add_format({'bold': True})
        value_fmt = workbook.add_format({'border': 1})

        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4F81BD', 'color': 'white', 'border': 1})
        cell_fmt = workbook.add_format({'border': 1})
        number_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        date_fmt = workbook.add_format({'border': 1, 'num_format': 'dd-mm-yyyy'})

        # -----------------------------
        # STANDARD AWT HEADER
        row = write_awt_excel_header(
            sheet, workbook, "Purchase Detail Report",
            date_from=from_date, date_to=to_date,
        )

        # -----------------------------
        # FILTER SECTION
        sheet.write(row, 0, 'Suppliers:', label_fmt)
        sheet.write(row, 1, ', '.join(suppliers) if suppliers else 'All', value_fmt)
        row += 1

        sheet.write(row, 0, 'Projects:', label_fmt)
        sheet.write(row, 1, ', '.join(projects) if projects else 'All', value_fmt)
        row += 1

        sheet.write(row, 0, 'UOM:', label_fmt)
        sheet.write(row, 1, uom or 'All', value_fmt)
        row += 1

        sheet.write(row, 0, 'City Locations:', label_fmt)
        sheet.write(row, 1, ', '.join(cities) if cities else 'All', value_fmt)
        row += 1

        # -----------------------------
        # TABLE HEADER
        headers = [
            'SR#', 'Date', 'Supplier', 'Bill No',
            'Ref No', 'Product', 'Qty', 'Rate', 'Amount'
        ]

        for col, h in enumerate(headers):
            sheet.write(row, col, h, header_fmt)

        # -----------------------------
        # DATA
        sr_no = 1

        for move in moves:
            for line in move.line_ids.filtered(lambda l: l.display_type == 'product'):

                # UOM filter
                if uom_id and line.product_uom_id.id != uom_id:
                    continue

                # City filter
                if city_location_ids and move.partner_id.city_location_id.id not in city_location_ids:
                    continue

                qty = line.quantity or 0
                rate = line.price_unit or 0
                amount = qty * rate

                row += 1

                sheet.write(row, 0, sr_no, cell_fmt)
                sheet.write(row, 1, move.invoice_date, date_fmt)
                sheet.write(row, 2, move.partner_id.name or '', cell_fmt)
                sheet.write(row, 3, move.id, cell_fmt)
                sheet.write(row, 4, move.name or '', cell_fmt)
                sheet.write(row, 5, line.product_id.name or '', cell_fmt)
                sheet.write(row, 6, qty, number_fmt)
                sheet.write(row, 7, rate, number_fmt)
                sheet.write(row, 8, amount, number_fmt)

                sr_no += 1
from odoo import api, models


class PurchaseDetailReportPreview(models.AbstractModel):
    _name = 'report.purchase_detail.report_preview'
    _description = 'Purchase Detail Report Preview (HTML)'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}

        from_date = data.get('from_date')
        to_date = data.get('to_date')
        supplier_ids = data.get('supplier_id') or []
        project_ids = data.get('project_ids') or []
        uom_id = data.get('uom_id')
        city_location_ids = data.get('city_location_ids') or []

        suppliers = self.env['res.partner'].browse(supplier_ids).mapped('name')
        projects = self.env['account.analytic.account'].browse(project_ids).mapped('name')
        uom = self.env['uom.uom'].browse(uom_id).name if uom_id else ''
        cities = self.env['city.location'].browse(city_location_ids).mapped('name')

        domain = [
            ('journal_id', '=', 10),
            ('state', '=', 'posted'),
        ]

        if from_date:
            domain.append(('invoice_date', '>=', from_date))

        if to_date:
            domain.append(('invoice_date', '<=', to_date))

        if supplier_ids:
            domain.append(('partner_id', 'in', supplier_ids))

        moves = self.env['account.move'].search(domain)

        rows = []
        sr_no = 1

        for move in moves:
            for line in move.line_ids.filtered(lambda l: l.display_type == 'product'):
                if uom_id and line.product_uom_id.id != uom_id:
                    continue

                if city_location_ids and move.partner_id.city_location_id.id not in city_location_ids:
                    continue

                qty = line.quantity or 0
                rate = line.price_unit or 0
                amount = qty * rate

                rows.append({
                    'sr_no': sr_no,
                    'invoice_date': move.invoice_date or '',
                    'supplier': move.partner_id.name or '',
                    'bill_no': move.id,
                    'ref_no': move.name or '',
                    'product': line.product_id.name or '',
                    'qty': qty,
                    'rate': rate,
                    'amount': amount,
                })
                sr_no += 1

        return {
            'doc_ids': docids,
            'doc_model': 'purchase.detail.report.wizard',
            'docs': self.env['purchase.detail.report.wizard'].browse(docids),
            'data': data,
            'from_date': from_date or '',
            'to_date': to_date or '',
            'suppliers': ', '.join(suppliers) if suppliers else 'All',
            'projects': ', '.join(projects) if projects else 'All',
            'uom': uom or 'All',
            'city_locations': ', '.join(cities) if cities else 'All',
            'rows': rows,
        }

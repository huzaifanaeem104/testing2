from odoo import models, fields, api

class StockValuationReportWizard(models.TransientModel):
    _name = 'stock.valuation.report.wizard'
    _description = 'Stock Valuation Report Wizard'

    from_date = fields.Date(string='Date From')
    to_date = fields.Date(string='Date To')
    product_id = fields.Many2one('product.product')

    def action_export_excel(self):
        # Pass branch_id as integer to the report
        data = {
            'from_date': self.from_date.strftime('%Y-%m-%d') if self.from_date else None,
            'to_date': self.to_date.strftime('%Y-%m-%d') if self.to_date else None,
            'product_id': self.product_id.id if self.product_id else None,
            'wizard_id': self.id,
        }

        return self.env.ref(
            'stock_valuation.action_stock_valuation_report_xlsx'
        ).report_action(self, data=data)


from odoo import models, fields, api


class PurchaseDetailReportWizard(models.TransientModel):
    _name = 'purchase.detail.report.wizard'
    _description = 'Purchase Detail Report Wizard'

    from_date = fields.Date(string='Date From')
    to_date = fields.Date(string='Date To')
    project_ids = fields.Many2many('account.analytic.account', string="Projects")
    uom_id = fields.Many2one("uom.uom", string='UOM')
    city_location_ids = fields.Many2many(
        'city.location',
        string='City Locations'
    )
    supplier_id = fields.Many2many(
        'res.partner',
        string='Supplier', )

    def _prepare_report_data(self):
        return {
            'from_date': self.from_date.strftime('%Y-%m-%d') if self.from_date else None,
            'to_date': self.to_date.strftime('%Y-%m-%d') if self.to_date else None,
            'supplier_id': self.supplier_id.ids if self.supplier_id else None,
            'project_ids': self.project_ids.ids,
            'uom_id': self.uom_id.id,
            'city_location_ids': self.city_location_ids.ids,
            'wizard_id': self.id,
        }

    def action_export_excel(self):
        return self.env.ref(
            'purchase_detail.action_purchase_detail_report_xlsx'
        ).report_action(self, data=self._prepare_report_data())

    def action_preview(self):
        return self.env.ref(
            'purchase_detail.action_purchase_detail_report_html'
        ).report_action(self, data=self._prepare_report_data())

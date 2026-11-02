from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    dairy_medicine_location_id = fields.Many2one(
        'stock.location', string='Medicine Store Location',
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [id, False])]")
    dairy_medicine_consumption_location_id = fields.Many2one(
        'stock.location', string='Medicine Consumption Location',
        domain="[('usage', '=', 'inventory'), ('company_id', 'in', [id, False])]",
        help='Virtual location receiving administered medicines. Its valuation account is the '
             'veterinary/medicine expense account under automated valuation.')

    def _dairy_health_setup_locations(self):
        Location = self.env['stock.location'].sudo()
        parent = self.env.ref('stock.stock_location_locations_virtual', raise_if_not_found=False)
        for company in self:
            warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
            if not warehouse:
                continue
            vals = {}
            if not company.dairy_medicine_location_id:
                vals['dairy_medicine_location_id'] = warehouse.lot_stock_id.id
            if not company.dairy_medicine_consumption_location_id:
                vals['dairy_medicine_consumption_location_id'] = Location.create({
                    'name': _('Medicine Consumption'), 'usage': 'inventory',
                    'location_id': parent.id if parent else False, 'company_id': company.id}).id
            if vals:
                company.sudo().write(vals)

    def _dairy_medicine_locations(self):
        self.ensure_one()
        if not (self.dairy_medicine_location_id and self.dairy_medicine_consumption_location_id):
            raise UserError(_('Configure the medicine store and consumption locations in Farm Settings for %s.',
                              self.name))
        return self.dairy_medicine_location_id, self.dairy_medicine_consumption_location_id

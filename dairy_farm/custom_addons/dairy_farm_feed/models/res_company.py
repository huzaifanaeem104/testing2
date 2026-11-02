from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    dairy_feed_location_id = fields.Many2one(
        'stock.location', string='Feed Store Location',
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [id, False])]",
        help='Internal location feed is issued from.')
    dairy_feed_consumption_location_id = fields.Many2one(
        'stock.location', string='Feed Consumption Location',
        domain="[('usage', '=', 'inventory'), ('company_id', 'in', [id, False])]",
        help='Virtual location receiving fed quantities. Its valuation account is the feed consumption '
             'expense account under automated valuation.')
    dairy_feed_wastage_location_id = fields.Many2one(
        'stock.location', string='Feed Wastage Location',
        domain="[('usage', '=', 'inventory'), ('company_id', 'in', [id, False])]")

    def _dairy_feed_setup_locations(self):
        """Create the dairy virtual locations for companies that have a warehouse."""
        Location = self.env['stock.location'].sudo()
        for company in self:
            warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
            if not warehouse:
                continue
            parent = self.env.ref('stock.stock_location_locations_virtual', raise_if_not_found=False)
            vals = {}
            if not company.dairy_feed_location_id:
                vals['dairy_feed_location_id'] = warehouse.lot_stock_id.id
            if not company.dairy_feed_consumption_location_id:
                vals['dairy_feed_consumption_location_id'] = Location.create({
                    'name': _('Feed Consumption'), 'usage': 'inventory',
                    'location_id': parent.id if parent else False, 'company_id': company.id}).id
            if not company.dairy_feed_wastage_location_id:
                scrap = Location.search([('scrap_location', '=', True), ('company_id', '=', company.id)], limit=1)
                vals['dairy_feed_wastage_location_id'] = scrap.id or Location.create({
                    'name': _('Feed Wastage'), 'usage': 'inventory', 'scrap_location': True,
                    'location_id': parent.id if parent else False, 'company_id': company.id}).id
            if vals:
                company.sudo().write(vals)

    def _dairy_feed_locations(self):
        self.ensure_one()
        if not (self.dairy_feed_location_id and self.dairy_feed_consumption_location_id
                and self.dairy_feed_wastage_location_id):
            raise UserError(_('Configure the feed store, consumption and wastage locations in '
                              'Dairy Farm > Configuration > Farm Settings for %s.', self.name))
        return self.dairy_feed_location_id, self.dairy_feed_consumption_location_id, self.dairy_feed_wastage_location_id

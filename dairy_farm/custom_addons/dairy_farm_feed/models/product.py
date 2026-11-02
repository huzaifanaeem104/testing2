from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_dairy_feed = fields.Boolean(string='Dairy Feed', index=True,
                                   help='Available for feeding plans and feed consumption.')

    @api.onchange('is_dairy_feed')
    def _onchange_is_dairy_feed(self):
        if self.is_dairy_feed:
            self.is_storable = True
            category = self.env.ref('dairy_farm_feed.product_category_dairy_feed', raise_if_not_found=False)
            if category and self.categ_id == self.env.ref('product.product_category_all'):
                self.categ_id = category

    def _dairy_low_stock_summary(self):
        return _('Low feed stock')

    @api.model
    def _cron_feed_stock_alerts(self):
        """Alert on feed products below their reordering-rule minimum (idempotent)."""
        orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('product_id.is_dairy_feed', '=', True), ('trigger', 'in', ('auto', 'manual'))])
        low, ok = self.browse(), self.browse()
        for op in orderpoints:
            template = op.product_id.product_tmpl_id
            qty = op.product_id.with_context(location=op.location_id.id).qty_available
            if qty < op.product_min_qty:
                low |= template
                template._dairy_alert_low_stock(qty, op)
            else:
                ok |= template
        (ok - low)._dairy_clear_low_stock()

    def _dairy_alert_low_stock(self, qty, orderpoint):
        summary = self._dairy_low_stock_summary()
        existing = self.env['mail.activity'].search_count([
            ('res_model', '=', 'product.template'), ('res_id', '=', self.id), ('summary', '=', summary)])
        if existing:
            return
        user = self.env.company.dairy_alert_user_id or self.env.ref('base.user_admin')
        self.activity_schedule(
            'mail.mail_activity_data_todo', summary=summary, user_id=user.id,
            note=_('%(qty)s %(uom)s on hand in %(loc)s, minimum %(min)s.',
                   qty=round(qty, 2), uom=self.uom_id.name, loc=orderpoint.location_id.display_name,
                   min=orderpoint.product_min_qty))

    def _dairy_clear_low_stock(self):
        if not self:
            return
        self.env['mail.activity'].search([
            ('res_model', '=', 'product.template'), ('res_id', 'in', self.ids),
            ('summary', '=', self._dairy_low_stock_summary())]).action_feedback(feedback=_('Stock replenished.'))

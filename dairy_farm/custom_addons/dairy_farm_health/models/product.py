from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_dairy_medicine = fields.Boolean(string='Veterinary Medicine', index=True)
    is_dairy_vaccine = fields.Boolean(string='Vaccine')
    dairy_milk_withdrawal_days = fields.Integer(
        string='Milk Withdrawal (days)',
        help='Label withdrawal period after the last administration. Milk of treated animals is '
             'withheld until a veterinarian releases it.')
    dairy_meat_withdrawal_days = fields.Integer(string='Meat Withdrawal (days)')
    dairy_revaccination_days = fields.Integer(
        string='Revaccination Interval (days)', help='Schedules the next dose automatically when > 0.')
    dairy_default_route = fields.Selection([
        ('im', 'Intramuscular'),
        ('iv', 'Intravenous'),
        ('sc', 'Subcutaneous'),
        ('oral', 'Oral'),
        ('intramammary', 'Intramammary'),
        ('topical', 'Topical'),
        ('intrauterine', 'Intrauterine'),
        ('other', 'Other'),
    ], string='Default Route')

    _sql_constraints = [
        ('dairy_withdrawal_positive', 'CHECK(dairy_milk_withdrawal_days >= 0 AND dairy_meat_withdrawal_days >= 0)',
         'Withdrawal periods cannot be negative.'),
    ]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('default_is_dairy_medicine') and 'categ_id' in fields_list \
                and 'default_categ_id' not in self.env.context:
            category = self.env.ref('dairy_farm_health.product_category_dairy_medicine', raise_if_not_found=False)
            if category:
                res['categ_id'] = category.id
        return res

    @api.onchange('is_dairy_medicine', 'is_dairy_vaccine')
    def _onchange_is_dairy_medicine(self):
        if self.is_dairy_vaccine:
            self.is_dairy_medicine = True
        if self.is_dairy_medicine:
            self.is_storable = True
            category = self.env.ref('dairy_farm_health.product_category_dairy_medicine', raise_if_not_found=False)
            if category and self.categ_id == self.env.ref('product.product_category_all'):
                self.categ_id = category

    def _dairy_medicine_low_summary(self):
        return _('Low medicine stock')

    @api.model
    def _cron_medicine_stock_alerts(self):
        """Alert on medicines below their reordering-rule minimum (idempotent)."""
        summary = self._dairy_medicine_low_summary()
        orderpoints = self.env['stock.warehouse.orderpoint'].search([('product_id.is_dairy_medicine', '=', True)])
        low = self.browse()
        for op in orderpoints:
            template = op.product_id.product_tmpl_id
            qty = op.product_id.with_context(location=op.location_id.id).qty_available
            if qty >= op.product_min_qty:
                continue
            low |= template
            if self.env['mail.activity'].search_count([('res_model', '=', 'product.template'),
                                                       ('res_id', '=', template.id), ('summary', '=', summary)]):
                continue
            user = op.company_id.dairy_alert_user_id or self.env.ref('base.user_admin')
            template.activity_schedule('mail.mail_activity_data_todo', summary=summary, user_id=user.id,
                                       note=_('%(qty)s %(uom)s on hand, minimum %(min)s.', qty=round(qty, 2),
                                              uom=template.uom_id.name, min=op.product_min_qty))
        resolved = orderpoints.product_id.product_tmpl_id - low
        self.env['mail.activity'].search([('res_model', '=', 'product.template'), ('res_id', 'in', resolved.ids),
                                          ('summary', '=', summary)]).action_feedback(feedback=_('Stock replenished.'))

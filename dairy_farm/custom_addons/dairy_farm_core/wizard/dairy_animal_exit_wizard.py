from odoo import _, fields, models
from odoo.exceptions import UserError


class DairyAnimalExitWizard(models.TransientModel):
    _name = 'dairy.animal.exit.wizard'
    _description = 'Record Animal Exit'

    animal_id = fields.Many2one('dairy.animal', required=True)
    exit_type = fields.Selection([
        ('sold', 'Sold'),
        ('deceased', 'Deceased'),
        ('inactive', 'Inactive / Culled'),
    ], required=True, default='sold')
    exit_date = fields.Date(required=True, default=fields.Date.context_today)
    exit_reason = fields.Text(required=True)
    buyer_id = fields.Many2one('res.partner', string='Buyer')
    sale_price = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='animal_id.currency_id')

    def action_confirm(self):
        self.ensure_one()
        animal = self.animal_id
        if animal.active_status != 'active':
            raise UserError(_('%s has already left the herd.', animal.display_name))
        vals = {
            'active_status': self.exit_type,
            'exit_date': self.exit_date,
            'exit_reason': self.exit_reason,
            'production_status': 'na',
            'active': False,
        }
        if self.exit_type == 'sold':
            vals.update(buyer_id=self.buyer_id.id, sale_price=self.sale_price)
        animal.write(vals)
        animal.message_post(body=_('Exit recorded: %(type)s on %(date)s. %(reason)s',
                                   type=dict(self._fields['exit_type'].selection)[self.exit_type],
                                   date=self.exit_date, reason=self.exit_reason))
        return {'type': 'ir.actions.act_window_close'}

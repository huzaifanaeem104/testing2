# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class AgesContract(models.Model):
    _inherit = 'ages.contract'

    def action_mobilization_receiving(self):
        """Open Mobilization Received prefilled from this contract (saved on create)."""
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('Mobilization Receiving is only available on Running contracts.'))
        if not (self.total_mobilization_amount or 0.0):
            raise UserError(_(
                'Mobilization Receiving is not available because Total Mobilization Amount is zero.'
            ))
        if self.mobilization_advance_id:
            return self._action_open_record(self.mobilization_advance_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mobilization Received'),
            'res_model': 'ages.mobilization.advance',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_contract_id': self.id,
                'default_project_id': self.project_id.id,
                'default_company_id': self.company_id.id,
                'default_mobilization_amount': self.total_mobilization_amount or 0.0,
                'default_date': fields.Date.context_today(self),
            },
        }

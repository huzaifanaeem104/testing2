# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class AgesGatePassReject(models.TransientModel):
    _name = 'ages.gate.pass.reject'
    _description = 'Reject Gate Pass'

    gate_pass_id = fields.Many2one(
        comodel_name='ages.gate.pass',
        required=True,
        ondelete='cascade',
    )
    reason = fields.Text(string='Reject Reason', required=True)

    def action_reject(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(self.env._('Please provide a reject reason.'))
        self.gate_pass_id.action_security_reject(self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}

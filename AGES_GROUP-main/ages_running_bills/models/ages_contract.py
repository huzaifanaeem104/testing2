# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgesContract(models.Model):
    _inherit = 'ages.contract'

    retention_percent = fields.Float(
        string='Retention (%)',
        digits=(16, 2),
        default=0.0,
        help='Share of the contract held as retention until close.\n'
             'Formula: Total Retention Amount = Retention Amount Base × Retention % / 100.',
    )
    running_bills_work_done = fields.Float(
        string='Running Bills Work Done',
        compute='_compute_can_create_ra_bill',
    )
    can_create_ra_bill = fields.Boolean(
        string='Can Create RA Bill',
        compute='_compute_can_create_ra_bill',
    )

    @api.depends(
        'total_work_done_value',
        'running_bill_ids.value_of_work_done',
        'running_bill_ids.state',
    )
    def _compute_can_create_ra_bill(self):
        for contract in self:
            bills = contract.running_bill_ids.filtered(lambda bill: bill.state != 'cancelled')
            total = sum(bills.mapped('value_of_work_done'))
            contract.running_bills_work_done = total
            contract.can_create_ra_bill = total < (contract.total_work_done_value or 0)

    def _check_can_create_ra_bill(self):
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('Running Bills can only be created for Running contracts.'))
        if not self.can_create_ra_bill:
            raise UserError(_(
                'Running Bills already cover the contract Total Work Done Value (%s). '
                'Unlock the contract, increase Total Work Done Value, then create another Running Bill.'
            ) % (self.total_work_done_value or 0))

    def action_create_ra_bill(self):
        """Create Running Bill prefilled from this contract."""
        self.ensure_one()
        self._check_can_create_ra_bill()
        bill = self.env['ages.running.bill'].create_from_contract(self)
        return self._action_open_record(bill)

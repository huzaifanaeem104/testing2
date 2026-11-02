# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgesContract(models.Model):
    _inherit = 'ages.contract'

    total_retention_amount = fields.Float(
        string='Total Retention Amount (Rs)',
        compute='_compute_total_retention_amount',
        inverse='_inverse_total_retention_amount',
        store=True,
        readonly=False,
        digits=(16, 2),
        help='Retention held on the full contract. Released later from Retention Release after the contract is closed.\n'
             'Formula: Retention Amount Base × Retention % / 100.',
    )

    @api.depends(
        'wth_tax_id',
        'wth_tax_id.amount',
        'wth_tax_id.amount_type',
        'work_done_ex_rebate_mr',
        'sales_tax_amount',
        'wth_on_sales_tax_amount',
        'total_mobilization_amount',
        'total_retention_amount',
        'wht_on_mobilization',
        'wht_on_retention',
    )
    def _compute_wth_amount(self):
        super()._compute_wth_amount()

    @api.depends(
        'retention_percent',
        'retention_amount_base',
        'total_work_done_value',
        'work_done_ex_rebate',
        'work_done_ex_rebate_mr',
    )
    def _compute_total_retention_amount(self):
        for contract in self:
            base = contract._get_amount_for_base(contract.retention_amount_base)
            contract.total_retention_amount = (contract.retention_percent or 0.0) / 100.0 * base

    def _inverse_total_retention_amount(self):
        return

    def action_retention_release(self):
        """Open Retention Release prefilled from this closed contract (saved on create)."""
        self.ensure_one()
        if self.state != 'closed':
            raise UserError(_('Retention Release is only available on Closed contracts.'))
        if not (self.total_retention_amount or 0.0):
            raise UserError(_(
                'Retention Release is not available because Total Retention Amount is zero.'
            ))
        if self.retention_recovery_id:
            return self._action_open_record(self.retention_recovery_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retention Release'),
            'res_model': 'ages.retention.recovery',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_contract_id': self.id,
                'default_project_id': self.project_id.id,
                'default_company_id': self.company_id.id,
                'default_retention_amount': self.total_retention_amount or 0.0,
                'default_date': fields.Date.context_today(self),
            },
        }

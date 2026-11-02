# -*- coding: utf-8 -*-

from odoo import api, fields, models


class GeneralLedgerWizard(models.TransientModel):
    _inherit = 'general.ledger.wizard'

    show_opal_balance = fields.Boolean(default=False)

    @api.model
    def get_filter_values(self, wizard_id):
        values = super().get_filter_values(wizard_id)
        wizard = self.browse(wizard_id).exists()
        if wizard:
            values['show_opal_balance'] = bool(wizard.show_opal_balance)
        return values

    @api.model
    def update_filters(self, wizard_id, filters):
        result = super().update_filters(wizard_id, filters)
        if 'show_opal_balance' in filters:
            wizard = self.browse(wizard_id).exists()
            if wizard:
                wizard.show_opal_balance = bool(filters['show_opal_balance'])
                if isinstance(result, dict):
                    result['show_opal_balance'] = wizard.show_opal_balance
        return result

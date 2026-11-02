# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        mapped_vals_list = [
            self._apply_sub_company_account_mapping(vals)
            for vals in vals_list
        ]
        return super().create(mapped_vals_list)

    def write(self, vals):
        if 'account_id' in vals:
            vals = self._apply_sub_company_account_mapping(vals, records=self)
        return super().write(vals)

    @api.model
    def _apply_sub_company_account_mapping(self, vals, records=None):
        """Map Old Account to New Account based on Sub Company configuration."""
        vals = dict(vals)
        account_id = vals.get('account_id')
        if not account_id:
            return vals

        company_id = vals.get('company_id')
        move = False
        if vals.get('move_id'):
            move = self.env['account.move'].browse(vals['move_id'])
            if not company_id:
                company_id = move.company_id.id
        elif records and len(records) == 1:
            move = records.move_id
            if not company_id:
                company_id = records.company_id.id

        if not company_id:
            return vals

        Mapping = self.env['ages.sub.company.account.mapping']
        domain = [
            ('company_id', '=', company_id),
            ('old_account_id', '=', account_id),
        ]
        if move and 'ages_sub_company_id' in move._fields and move.ages_sub_company_id:
            domain.append(('sub_company_id', '=', move.ages_sub_company_id.id))

        mapping = Mapping.search(domain, limit=1)
        if mapping:
            vals['account_id'] = mapping.new_account_id.id
        return vals

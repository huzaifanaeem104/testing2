# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AgesSubCompanyAccountMapping(models.Model):
    _name = 'ages.sub.company.account.mapping'
    _description = 'Sub Company Account Mapping'
    _order = 'id'

    sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Sub Company',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='sub_company_id.company_id',
        store=True,
        readonly=True,
    )
    old_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Old Account (Default)',
        required=True,
        domain="[('company_ids', 'in', company_id)]",
    )
    new_account_id = fields.Many2one(
        comodel_name='account.account',
        string='New Account (Replacement)',
        required=True,
        domain="[('company_ids', 'in', company_id)]",
    )

    _sql_constraints = [
        (
            'sub_company_old_account_uniq',
            'unique(sub_company_id, old_account_id)',
            'Each Old Account can only be mapped once per Sub Company.',
        ),
    ]

    @api.constrains('old_account_id', 'new_account_id', 'company_id')
    def _check_account_mapping(self):
        for record in self:
            if record.old_account_id == record.new_account_id:
                raise ValidationError(_('Old Account and New Account must be different.'))
            for account, label in (
                (record.old_account_id, _('Old Account')),
                (record.new_account_id, _('New Account')),
            ):
                if record.company_id and record.company_id not in account.company_ids:
                    raise ValidationError(
                        _('%s must belong to the selected company.') % label
                    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._apply_account_replacement()
        return records

    def write(self, vals):
        account_fields = {'old_account_id', 'new_account_id'}
        should_replace = bool(account_fields & set(vals.keys()))
        result = super().write(vals)
        if should_replace:
            self._apply_account_replacement()
        return result

    def _apply_account_replacement(self):
        """Replace Old Account with New Account on journal items of the company."""
        AccountMoveLine = self.env['account.move.line']
        for record in self:
            if not record.old_account_id or not record.new_account_id:
                continue
            if record.old_account_id == record.new_account_id:
                continue
            domain = [
                ('company_id', '=', record.company_id.id),
                ('account_id', '=', record.old_account_id.id),
            ]
            Move = self.env['account.move']
            if 'ages_sub_company_id' in Move._fields:
                domain.append(('move_id.ages_sub_company_id', '=', record.sub_company_id.id))
            lines = AccountMoveLine.search(domain)
            if lines:
                lines.write({'account_id': record.new_account_id.id})

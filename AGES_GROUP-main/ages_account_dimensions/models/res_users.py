# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command


class ResUsers(models.Model):
    _inherit = 'res.users'

    ages_hide_users_bills = fields.Boolean(
        string='Hide Users Bills',
        compute='_compute_ages_misc_rights',
        inverse='_inverse_ages_hide_users_bills',
        help='This user only sees vendor bills they created. Other users’ bills are hidden.',
    )
    ages_hide_users_jes = fields.Boolean(
        string='Hide Users JEs',
        compute='_compute_ages_misc_rights',
        inverse='_inverse_ages_hide_users_jes',
        help='This user only sees journal entries they created. Other users’ journal entries are hidden.',
    )

    def _ages_misc_right_group(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    @api.depends('groups_id')
    def _compute_ages_misc_rights(self):
        bills_group = self._ages_misc_right_group(
            'ages_account_dimensions.group_hide_other_users_bills'
        )
        jes_group = self._ages_misc_right_group(
            'ages_account_dimensions.group_hide_other_users_jes'
        )
        for user in self:
            user.ages_hide_users_bills = bool(bills_group) and bills_group in user.groups_id
            user.ages_hide_users_jes = bool(jes_group) and jes_group in user.groups_id

    def _ages_set_misc_right_group(self, xmlid, enabled):
        group = self._ages_misc_right_group(xmlid)
        if not group:
            return
        for user in self:
            in_group = group in user.groups_id
            if enabled and not in_group:
                super(ResUsers, user).write({'groups_id': [Command.link(group.id)]})
            elif not enabled and in_group:
                super(ResUsers, user).write({'groups_id': [Command.unlink(group.id)]})

    def _inverse_ages_hide_users_bills(self):
        for user in self:
            user._ages_set_misc_right_group(
                'ages_account_dimensions.group_hide_other_users_bills',
                user.ages_hide_users_bills,
            )

    def _inverse_ages_hide_users_jes(self):
        for user in self:
            user._ages_set_misc_right_group(
                'ages_account_dimensions.group_hide_other_users_jes',
                user.ages_hide_users_jes,
            )

    @api.model_create_multi
    def create(self, vals_list):
        flags = []
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            flags.append({
                'bills': vals.pop('ages_hide_users_bills', False),
                'jes': vals.pop('ages_hide_users_jes', False),
            })
            prepared.append(vals)
        users = super().create(prepared)
        for user, flag in zip(users, flags):
            if flag['bills']:
                user._ages_set_misc_right_group(
                    'ages_account_dimensions.group_hide_other_users_bills',
                    True,
                )
            if flag['jes']:
                user._ages_set_misc_right_group(
                    'ages_account_dimensions.group_hide_other_users_jes',
                    True,
                )
        return users

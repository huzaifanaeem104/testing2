# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'button.access.restrict.mixin']

    # Reuses the exact same relation table/columns as
    # button.access.rule.user_ids with the two columns swapped.
    button_access_rule_ids = fields.Many2many(
        'button.access.rule', 'button_access_rule_users_rel', 'user_id', 'rule_id',
        string='Hidden Buttons',
        help='Buttons currently hidden (and blocked) for this user, whether '
             'model-specific or applied to all models at once.')

    button_access_rule_count = fields.Integer(
        string='Hidden Buttons Count', compute='_compute_button_access_rule_count')

    hidden_menu_rule_ids = fields.Many2many(
        'button.access.menu.rule', 'button_access_menu_rule_users_rel',
        'user_id', 'rule_id', string='Hidden App / Menu Rules')
    hidden_home_app_ids = fields.Many2many(
        'ir.ui.menu', compute='_compute_hidden_home_app_ids',
        inverse='_inverse_hidden_home_app_ids',
        string='Hidden Home Apps',
        domain="[('parent_id', '=', False)]",
        context={'ir.ui.menu.full_list': True},
        help='Direct home-app hides for this user. Group/profile hides still '
             'apply at runtime even if an app is not listed here.')
    hidden_submenu_count = fields.Integer(
        compute='_compute_hidden_home_app_ids')

    @api.depends('button_access_rule_ids')
    def _compute_button_access_rule_count(self):
        for user in self:
            user.button_access_rule_count = len(user.button_access_rule_ids)

    @api.depends('hidden_menu_rule_ids', 'hidden_menu_rule_ids.menu_id',
                 'hidden_menu_rule_ids.is_root')
    def _compute_hidden_home_app_ids(self):
        for user in self:
            rules = user.hidden_menu_rule_ids.filtered(lambda r: r.active)
            user.hidden_home_app_ids = rules.filtered('is_root').mapped('menu_id')
            user.hidden_submenu_count = len(rules.filtered(lambda r: not r.is_root))

    def _inverse_hidden_home_app_ids(self):
        if self.env.context.get('access_profile_clearing'):
            return
        Rule = self.env['button.access.menu.rule'].sudo()
        for user in self:
            if not user.id or user.id == 1:
                continue
            wanted = set(user.hidden_home_app_ids.ids)
            existing = Rule.search([
                ('user_ids', 'in', [user.id]),
                ('is_root', '=', True),
            ])
            existing_ids = set(existing.mapped('menu_id').ids)
            for menu_id in wanted - existing_ids:
                Rule._create_or_update_menu_rule(menu_id, user_ids=[user.id])
            for menu_id in existing_ids - wanted:
                Rule._remove_user_from_menu_rule(menu_id, user.id)

    def _button_access_target_domain(self):
        self.ensure_one()
        return [('user_ids', 'in', [self.id])]

    def _button_access_add_global(self, button_type, alias, label):
        self.env['button.access.rule'].sudo()._create_or_update_global_rule(
            button_type, alias, label, user_id=self.id)

    def _button_access_remove_global(self, button_type, alias):
        self.env['button.access.rule'].sudo()._remove_user_from_global_rule(
            button_type, alias, self.id)

    def action_open_hidden_apps_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Hide Apps & Menus'),
            'res_model': 'button.access.menu.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_user_ids': [(6, 0, [self.id])],
                'lock_user_field': True,
            },
        }

    def action_preview_home_screen(self):
        self.ensure_one()
        wizard = self.env['button.access.menu.wizard'].create({
            'user_ids': [(6, 0, [self.id])],
        })
        return wizard.action_preview()

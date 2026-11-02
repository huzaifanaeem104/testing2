# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResGroups(models.Model):
    _name = 'res.groups'
    _inherit = ['res.groups', 'button.access.restrict.mixin']

    button_access_rule_ids = fields.Many2many(
        'button.access.rule', 'button_access_rule_groups_rel', 'group_id', 'rule_id',
        string='Hidden Buttons',
        help='Buttons currently hidden (and blocked) for every user in this group.')

    hidden_menu_rule_ids = fields.Many2many(
        'button.access.menu.rule', 'button_access_menu_rule_groups_rel',
        'group_id', 'rule_id', string='Hidden App / Menu Rules')
    hidden_home_app_ids = fields.Many2many(
        'ir.ui.menu', compute='_compute_hidden_home_app_ids',
        inverse='_inverse_hidden_home_app_ids',
        string='Hidden Home Apps',
        domain="[('parent_id', '=', False)]",
        context={'ir.ui.menu.full_list': True})
    hidden_submenu_count = fields.Integer(compute='_compute_hidden_home_app_ids')

    @api.depends('hidden_menu_rule_ids', 'hidden_menu_rule_ids.menu_id',
                 'hidden_menu_rule_ids.is_root')
    def _compute_hidden_home_app_ids(self):
        for group in self:
            rules = group.hidden_menu_rule_ids.filtered(lambda r: r.active)
            group.hidden_home_app_ids = rules.filtered('is_root').mapped('menu_id')
            group.hidden_submenu_count = len(rules.filtered(lambda r: not r.is_root))

    def _inverse_hidden_home_app_ids(self):
        if self.env.context.get('access_profile_clearing'):
            return
        Rule = self.env['button.access.menu.rule'].sudo()
        Profile = self.env['access.profile'].sudo().with_context(active_test=False)
        for group in self:
            if not group.id:
                continue
            if Profile.search_count([('generated_group_id', '=', group.id)]):
                continue
            wanted = set(group.hidden_home_app_ids.ids)
            existing = Rule.search([
                ('group_ids', 'in', [group.id]),
                ('is_root', '=', True),
            ])
            existing_ids = set(existing.mapped('menu_id').ids)
            for menu_id in wanted - existing_ids:
                Rule._create_or_update_menu_rule(menu_id, group_ids=[group.id])
            for menu_id in existing_ids - wanted:
                Rule._remove_group_from_menu_rule(menu_id, group.id)

    def _button_access_target_domain(self):
        self.ensure_one()
        return [('group_ids', 'in', [self.id])]

    def _button_access_add_global(self, button_type, alias, label):
        self.env['button.access.rule'].sudo()._create_or_update_global_rule(
            button_type, alias, label, group_id=self.id)

    def _button_access_remove_global(self, button_type, alias):
        self.env['button.access.rule'].sudo()._remove_group_from_global_rule(
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
                'default_group_ids': [(6, 0, [self.id])],
                'lock_group_field': True,
            },
        }

# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

from odoo.addons.button_access_manager.models.constants import is_framework_model


class AccessProfileSimulator(models.TransientModel):
    _name = 'access.profile.simulator'
    _description = 'Access Profile User Simulator'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    profile_id = fields.Many2one(
        'access.profile', string='Assign Profile',
        help='Optional. Used by Assign Profile.')
    group_names = fields.Text(readonly=True)
    hidden_buttons = fields.Text(readonly=True)
    hidden_menus = fields.Text(readonly=True)
    line_ids = fields.One2many(
        'access.profile.simulator.line', 'wizard_id', string='Effective CRUD')

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            self._populate_preview()

    def action_refresh(self):
        self.ensure_one()
        self._populate_preview()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _populate_preview(self):
        self.ensure_one()
        user = self.user_id
        self.group_names = '\n'.join(sorted(user.groups_id.mapped('name'))) or _('(no groups)')
        Rule = self.env['button.access.rule']
        rules = Rule.with_user(user).get_rules_for_current_user()
        lines = []
        for rule in rules[:80]:
            scope = rule['model'] or 'ALL MODELS'
            lines.append('%s / %s / %s' % (scope, rule['type'], rule['name'] or rule['string'] or ''))
        if len(rules) > 80:
            lines.append(_('… %s more', len(rules) - 80))
        self.hidden_buttons = '\n'.join(lines) or _('(none)')
        MenuRule = self.env['button.access.menu.rule'].sudo()
        hidden_ids = MenuRule.hidden_menu_ids_expanded_for_uid(user.id)
        if hidden_ids:
            menus = self.env['ir.ui.menu'].sudo().with_context(
                {'ir.ui.menu.full_list': True, 'active_test': False}
            ).browse(list(hidden_ids))
            self.hidden_menus = '\n'.join(
                sorted(menus.mapped('complete_name'))
            ) or _('(none)')
        else:
            self.hidden_menus = _('(none)')
        self.line_ids = [(5, 0, 0)]
        names = []
        actions = self.env['ir.actions.act_window'].sudo().search([('res_model', '!=', False)])
        for name in sorted(set(actions.mapped('res_model'))):
            if not name or name not in self.env or is_framework_model(self.env, name):
                continue
            names.append(name)
        commands = []
        for name in names[:120]:
            empty = self.env[name].with_user(user).browse()
            try:
                commands.append((0, 0, {
                    'model_name': name,
                    'perm_read': empty.has_access('read'),
                    'perm_write': empty.has_access('write'),
                    'perm_create': empty.has_access('create'),
                    'perm_unlink': empty.has_access('unlink'),
                }))
            except Exception:
                continue
        self.line_ids = commands

    def action_assign_profile(self):
        self.ensure_one()
        if not self.profile_id or not self.user_id:
            return True
        self.profile_id.write({'user_ids': [(4, self.user_id.id)]})
        self._populate_preview()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class AccessProfileSimulatorLine(models.TransientModel):
    _name = 'access.profile.simulator.line'
    _description = 'Access Profile Simulator Line'

    wizard_id = fields.Many2one('access.profile.simulator', ondelete='cascade')
    model_name = fields.Char(readonly=True)
    perm_read = fields.Boolean(string='Read', readonly=True)
    perm_write = fields.Boolean(string='Write', readonly=True)
    perm_create = fields.Boolean(string='Create', readonly=True)
    perm_unlink = fields.Boolean(string='Delete', readonly=True)

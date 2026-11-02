# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class ButtonAccessCopyWizard(models.TransientModel):
    _name = 'button.access.copy.wizard'
    _description = 'Copy Hidden Buttons'

    source_user_id = fields.Many2one('res.users', string='Copy From User')
    source_group_id = fields.Many2one('res.groups', string='Copy From Group')
    target_user_ids = fields.Many2many(
        'res.users', 'button_access_copy_wizard_target_users_rel',
        'wizard_id', 'user_id', string='Copy To Users')
    target_group_ids = fields.Many2many(
        'res.groups', 'button_access_copy_wizard_target_groups_rel',
        'wizard_id', 'group_id', string='Copy To Groups')
    copy_buttons = fields.Boolean(string='Copy hidden buttons', default=True)
    copy_menus = fields.Boolean(string='Copy hidden apps & menus', default=True)

    def action_copy(self):
        self.ensure_one()
        if not self.source_user_id and not self.source_group_id:
            raise UserError(_('Select a source user or source group.'))
        if not self.target_user_ids and not self.target_group_ids:
            raise UserError(_('Select at least one target user or group.'))
        if not self.copy_buttons and not self.copy_menus:
            raise UserError(_('Tick at least one of: hidden buttons, hidden apps & menus.'))
        copied = False
        if self.copy_buttons:
            if self.source_user_id:
                rules = self.source_user_id.button_access_rule_ids
            else:
                rules = self.source_group_id.button_access_rule_ids
            for rule in rules:
                vals = {}
                if self.target_user_ids:
                    vals['user_ids'] = [(4, uid) for uid in self.target_user_ids.ids if uid != 1]
                if self.target_group_ids:
                    vals['group_ids'] = [(4, gid) for gid in self.target_group_ids.ids]
                if vals:
                    rule.write(vals)
                    copied = True
        if self.copy_menus:
            if self.source_user_id:
                menu_rules = self.source_user_id.hidden_menu_rule_ids
            else:
                menu_rules = self.source_group_id.hidden_menu_rule_ids
            for rule in menu_rules:
                vals = {}
                if self.target_user_ids:
                    vals['user_ids'] = [(4, uid) for uid in self.target_user_ids.ids if uid != 1]
                if self.target_group_ids:
                    vals['group_ids'] = [(4, gid) for gid in self.target_group_ids.ids]
                if vals:
                    rule.write(vals)
                    copied = True
        if not copied:
            raise UserError(_('The source has no hidden-button or hidden-menu rules to copy.'))
        return {'type': 'ir.actions.act_window_close'}

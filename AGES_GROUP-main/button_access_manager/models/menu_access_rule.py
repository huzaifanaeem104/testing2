# -*- coding: utf-8 -*-
import logging
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .constants import (
    MENU_HIDE_TOKEN_PARAM,
    extra_protected_menus,
    protected_menu_ids,
)

_logger = logging.getLogger(__name__)

ACCESS_ERROR_MSG = (
    "This action has been restricted for your user account. "
    "Please contact your administrator if you believe this is a mistake."
)
LOCKOUT_MSG = (
    "You cannot hide Settings / Access Profiles from your own administrator account."
)


class ButtonAccessMenuRule(models.Model):
    _name = 'button.access.menu.rule'
    _description = 'Hidden App / Menu Rule'
    _rec_name = 'display_name'
    _order = 'menu_complete, id'

    menu_id = fields.Many2one(
        'ir.ui.menu', string='Menu', required=True, ondelete='cascade', index=True)
    menu_complete = fields.Char(
        compute='_compute_menu_complete', store=True, string='Full Path')
    is_root = fields.Boolean(compute='_compute_is_root', store=True, index=True)
    user_ids = fields.Many2many(
        'res.users', 'button_access_menu_rule_users_rel', 'rule_id', 'user_id',
        string='Hide From Users')
    group_ids = fields.Many2many(
        'res.groups', 'button_access_menu_rule_groups_rel', 'rule_id', 'group_id',
        string='Hide From Groups')
    active = fields.Boolean(default=True)
    note = fields.Text()
    uniq_key = fields.Char(
        compute='_compute_uniq_key', store=True, index=True)
    display_name = fields.Char(compute='_compute_display_name')

    _sql_constraints = [
        ('uniq_key', 'unique(uniq_key)',
         'A hide rule for this menu already exists. Add users or groups to it '
         'instead of creating a duplicate.'),
    ]

    @api.depends('menu_id', 'menu_id.name', 'menu_id.parent_id', 'menu_id.complete_name')
    def _compute_menu_complete(self):
        for rec in self:
            rec.menu_complete = rec.menu_id.complete_name if rec.menu_id else False

    @api.depends('menu_id', 'menu_id.parent_id')
    def _compute_is_root(self):
        for rec in self:
            rec.is_root = bool(rec.menu_id) and not rec.menu_id.parent_id

    @api.depends('menu_id')
    def _compute_uniq_key(self):
        for rec in self:
            rec.uniq_key = str(rec.menu_id.id or 0)

    @api.depends('menu_complete', 'menu_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.menu_complete or rec.menu_id.display_name or _('Menu')

    def _strip_superuser(self, user_ids):
        return [uid for uid in (user_ids or []) if uid and uid != 1]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            commands = vals.get('user_ids')
            if commands:
                vals['user_ids'] = self._filter_user_commands(commands)
        records = super().create(vals_list)
        empty = records.filtered(lambda r: not r.user_ids and not r.group_ids)
        if empty:
            raise ValidationError(_(
                "A hidden app/menu rule must hide the menu from at least one user or group."
            ))
        records._check_lockout()
        records._clear_menu_hide_cache()
        return records

    def write(self, vals):
        if 'user_ids' in vals:
            vals = dict(vals)
            vals['user_ids'] = self._filter_user_commands(vals['user_ids'])
        res = super().write(vals)
        if 'user_ids' in vals or 'group_ids' in vals or 'menu_id' in vals or 'active' in vals:
            empty = self.filtered(lambda r: r.exists() and not r.user_ids and not r.group_ids)
            if empty:
                empty.unlink()
                remaining = self - empty
            else:
                remaining = self.filtered('id')
            if remaining:
                remaining._check_lockout()
        self._clear_menu_hide_cache()
        return res

    def unlink(self):
        self._clear_menu_hide_cache()
        return super().unlink()

    def _filter_user_commands(self, commands):
        """Drop uid=1 from many2many commands."""
        if not commands:
            return commands
        filtered = []
        for command in commands:
            if not command:
                filtered.append(command)
                continue
            code = command[0]
            if code == 4 and len(command) > 1 and command[1] == 1:
                continue
            if code == 6 and len(command) > 2:
                ids = self._strip_superuser(command[2] or [])
                filtered.append((6, 0, ids))
                continue
            if code == 0 and len(command) > 2 and isinstance(command[2], dict):
                continue
            filtered.append(command)
        return filtered

    def _affected_users(self):
        users = self.mapped('user_ids')
        groups = self.mapped('group_ids')
        if groups:
            users |= self.env['res.users'].sudo().search([
                ('groups_id', 'in', groups.ids),
                ('id', '!=', 1),
            ])
        return users.filtered(lambda u: u.id != 1)

    def _check_lockout(self):
        protected = protected_menu_ids(self.env)
        if not protected:
            return
        system = self.env.ref('base.group_system', raise_if_not_found=False)
        if not system:
            return
        for rec in self:
            if rec.menu_id.id not in protected:
                continue
            admins = rec._affected_users().filtered(
                lambda u: system in u.groups_id)
            if admins:
                raise UserError(_(LOCKOUT_MSG))
            if (
                self.env.user.has_group('base.group_system')
                and self.env.uid != 1
                and (
                    self.env.uid in rec.user_ids.ids
                    or bool(set(self.env.user.groups_id.ids) & set(rec.group_ids.ids))
                )
            ):
                raise UserError(_(LOCKOUT_MSG))

    def _clear_menu_hide_cache(self):
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            current = int(ICP.get_param(MENU_HIDE_TOKEN_PARAM, '0') or 0)
            ICP.set_param(MENU_HIDE_TOKEN_PARAM, str(current + 1))
        except Exception:
            _logger.exception('button_access_manager: could not bump menu hide token')
        extra = getattr(self.env.cr, '_button_access_extra_protected_menus', None)
        if extra is not None:
            delattr(self.env.cr, '_button_access_extra_protected_menus')
        extra_protected_menus(self.env)
        for attr in (
            '_button_access_menu_hidden_by_uid',
            '_button_access_menu_expanded_by_uid',
        ):
            cache = getattr(self.env.cr, attr, None)
            if cache is not None:
                cache.clear()
        self.env.registry.clear_cache()

    @api.model
    def _menu_hide_cache_token(self):
        try:
            return self.env['ir.config_parameter'].sudo().get_param(
                MENU_HIDE_TOKEN_PARAM, '0') or '0'
        except Exception:
            return '0'

    def _target_domain_for_uid(self, uid):
        return self.env['button.access.rule']._target_domain_for_uid(uid)

    @api.model
    def hidden_menu_ids_for_uid(self, uid):
        if not uid or uid == 1:
            return set()
        cache = getattr(self.env.cr, '_button_access_menu_hidden_by_uid', None)
        if cache is None:
            cache = {}
            self.env.cr._button_access_menu_hidden_by_uid = cache
        key = (uid, self.env.company.id)
        if key not in cache:
            domain = [('active', '=', True)] + self._target_domain_for_uid(uid)
            rules = self.sudo().search(domain)
            cache[key] = set(rules.mapped('menu_id').ids)
        return set(cache[key])

    @api.model
    def _child_ids(self, menu_ids):
        if not menu_ids:
            return []
        return self.env['ir.ui.menu'].sudo().with_context(
            {'ir.ui.menu.full_list': True, 'active_test': False}
        ).search([('id', 'child_of', list(menu_ids))]).ids

    @api.model
    def _foreign_hidden_menu_ids(self, uid):
        """Union with Access Manager Ninja if it is installed (no dependency)."""
        ids = set()
        if not uid or uid == 1 or 'user.management' not in self.env:
            return ids
        try:
            recs = self.env['user.management'].sudo().search([
                ('ks_user_ids', 'in', [uid]),
                ('active', '=', True),
            ])
            ids.update(recs.mapped('ks_hide_menu_ids').ids)
        except Exception:
            return set()
        return ids

    @api.model
    def expand_hidden_menu_ids(self, explicit_ids):
        explicit_ids = set(explicit_ids or [])
        if not explicit_ids:
            return set()
        cache = getattr(self.env.cr, '_button_access_menu_expanded_by_uid', None)
        if cache is None:
            cache = {}
            self.env.cr._button_access_menu_expanded_by_uid = cache
        key = (frozenset(explicit_ids), self.env.company.id)
        if key in cache:
            hidden = set(cache[key])
        else:
            hidden = self._expand_hidden_menu_ids_compute(explicit_ids)
            cache[key] = set(hidden)
        hidden -= protected_menu_ids(self.env)
        return hidden

    def _expand_hidden_menu_ids_compute(self, explicit_ids):
        Menu = self.env['ir.ui.menu'].sudo().with_context(
            {'ir.ui.menu.full_list': True, 'active_test': False})
        hidden = set(self._child_ids(explicit_ids))
        roots = set()
        for mid in explicit_ids:
            menu = Menu.browse(mid)
            while menu.parent_id:
                menu = menu.parent_id
            if menu:
                roots.add(menu.id)
        if not roots:
            return hidden
        tree = Menu.search([('id', 'child_of', list(roots))])
        children_map = defaultdict(list)
        has_action = {}
        for menu in tree:
            has_action[menu.id] = bool(menu.action)
            if menu.parent_id:
                children_map[menu.parent_id.id].append(menu.id)

        def has_visible_action_descendant(menu_id):
            stack = list(children_map.get(menu_id, ()))
            seen = set()
            while stack:
                current = stack.pop()
                if current in seen or current in hidden:
                    continue
                seen.add(current)
                if has_action.get(current):
                    return True
                stack.extend(children_map.get(current, ()))
            return False

        changed = True
        while changed:
            changed = False
            for menu in tree:
                if menu.id in hidden or has_action.get(menu.id):
                    continue
                if not has_visible_action_descendant(menu.id):
                    hidden.add(menu.id)
                    changed = True
        return hidden

    @api.model
    def hidden_menu_ids_expanded_for_uid(self, uid):
        if not uid or uid == 1:
            return set()
        explicit = self.hidden_menu_ids_for_uid(uid) | self._foreign_hidden_menu_ids(uid)
        return self.expand_hidden_menu_ids(explicit)

    def is_menu_hidden(self, menu):
        if self.env.uid == 1:
            return False
        menu_id = menu.id if getattr(menu, 'id', None) else menu
        if not menu_id:
            return False
        return menu_id in self.hidden_menu_ids_expanded_for_uid(self.env.uid)

    @api.model
    def get_installed_home_apps(self):
        Menu = self.env['ir.ui.menu'].with_context({'ir.ui.menu.full_list': True})
        roots = Menu.search([('parent_id', '=', False), ('active', '=', True)])
        xmlids = roots._get_menuitems_xmlids()
        Module = self.env['ir.module.module'].sudo()
        rows = []
        for menu in roots:
            xmlid = xmlids.get(menu.id, '') or ''
            module_name = xmlid.split('.')[0] if xmlid else 'custom'
            module = Module.search([('name', '=', module_name)], limit=1) if module_name != 'custom' else Module.browse()
            if module and module.state in ('uninstalled', 'uninstallable', 'to remove'):
                continue
            is_application = bool(module.application) if module else bool(menu.web_icon or menu.web_icon_data)
            rows.append({
                'menu_id': menu.id,
                'name': menu.name,
                'xmlid': xmlid,
                'module_name': module_name,
                'module_shortdesc': module.shortdesc if module else '',
                'is_application': is_application,
                'web_icon_data': menu.web_icon_data,
                'child_count': Menu.search_count([('parent_id', '=', menu.id)]),
            })

        def sort_key(row):
            if row['is_application']:
                bucket = 0
            elif row['web_icon_data'] or row['module_name'] not in ('base', 'web', 'custom'):
                bucket = 1
            else:
                bucket = 2
            return (bucket, (row['name'] or '').lower())

        rows.sort(key=sort_key)
        return rows

    @api.model
    def _create_or_update_menu_rule(self, menu_id, user_ids=None, group_ids=None):
        user_ids = self._strip_superuser(user_ids)
        group_ids = list(group_ids or [])
        if not menu_id or (not user_ids and not group_ids):
            return self.browse()
        existing = self.search([('menu_id', '=', menu_id)], limit=1)
        if existing:
            vals = {'active': True}
            if user_ids:
                vals['user_ids'] = [(4, uid) for uid in user_ids]
            if group_ids:
                vals['group_ids'] = [(4, gid) for gid in group_ids]
            existing.write(vals)
            return existing
        return self.create({
            'menu_id': menu_id,
            'user_ids': [(6, 0, user_ids)] if user_ids else False,
            'group_ids': [(6, 0, group_ids)] if group_ids else False,
        })

    @api.model
    def _remove_user_from_menu_rule(self, menu_id, user_id):
        existing = self.search([
            ('menu_id', '=', menu_id),
            ('user_ids', 'in', [user_id]),
        ], limit=1)
        if existing:
            existing.write({'user_ids': [(3, user_id)]})

    @api.model
    def _remove_group_from_menu_rule(self, menu_id, group_id):
        existing = self.search([
            ('menu_id', '=', menu_id),
            ('group_ids', 'in', [group_id]),
        ], limit=1)
        if existing:
            existing.write({'group_ids': [(3, group_id)]})

    def _menus_for_action(self, action):
        if not action:
            return self.env['ir.ui.menu']
        ref = '%s,%s' % (action._name, action.id)
        return self.env['ir.ui.menu'].sudo().with_context(
            {'ir.ui.menu.full_list': True, 'active_test': False}
        ).search([('action', '=', ref)])

    def _is_action_fully_hidden(self, action):
        menus = self._menus_for_action(action)
        if not menus:
            return False
        hidden = self.hidden_menu_ids_expanded_for_uid(self.env.uid)
        return all(menu.id in hidden for menu in menus)

    def enforce_action(self, action):
        if not action or self.env.uid == 1 or self.env.context.get('button_access_skip'):
            return
        try:
            blocked = self._is_action_fully_hidden(action)
        except AccessError:
            raise
        except Exception:
            _logger.exception(
                'button_access_manager: menu enforcement failed, denying action.')
            raise AccessError(_(ACCESS_ERROR_MSG))
        if blocked:
            xmlid = ''
            try:
                xmlid = action.get_external_id().get(action.id) or ''
            except Exception:
                xmlid = ''
            technical = xmlid or str(action.id)
            model_name = (
                getattr(action, 'res_model', False)
                or getattr(action, 'model', False)
                or ''
            )
            _logger.info(
                'button_access_manager: blocked menu action uid=%s action=%s',
                self.env.uid, technical)
            if 'access.block.log' in self.env:
                try:
                    self.env['access.block.log'].sudo().create({
                        'user_id': self.env.uid,
                        'model_name': model_name or '',
                        'button_type': 'menu',
                        'technical_name': technical,
                    })
                except Exception:
                    _logger.exception(
                        'button_access_manager: could not write access.block.log')
            raise AccessError(_(ACCESS_ERROR_MSG))

# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ButtonAccessMenuWizard(models.TransientModel):
    _name = 'button.access.menu.wizard'
    _description = 'Hide Apps & Menus'

    user_ids = fields.Many2many(
        'res.users', 'button_access_menu_wizard_users_rel',
        'wizard_id', 'user_id', string='Hide From Users')
    group_ids = fields.Many2many(
        'res.groups', 'button_access_menu_wizard_groups_rel',
        'wizard_id', 'group_id', string='Hide From Groups')
    profile_id = fields.Many2one('access.profile', ondelete='cascade')
    app_menu_id = fields.Many2one(
        'ir.ui.menu', string='App',
        domain="[('parent_id', '=', False)]",
        context={'ir.ui.menu.full_list': True})
    line_ids = fields.One2many(
        'button.access.menu.wizard.line', 'wizard_id', string='Menus')
    preview_text = fields.Text(readonly=True)
    hidden_summary = fields.Char(compute='_compute_hidden_summary')

    @api.depends('line_ids.hide', 'line_ids.is_root')
    def _compute_hidden_summary(self):
        for wiz in self:
            roots = wiz.line_ids.filtered(lambda l: l.hide and l.is_root)
            extra = wiz.line_ids.filtered(lambda l: l.hide and not l.is_root and not l.hidden_by_parent)
            wiz.hidden_summary = _(
                '%(apps)s home app(s) and %(menus)s extra menu(s) marked to hide',
                apps=len(roots), menus=len(extra),
            )

    def _target_ok(self):
        return bool(self.user_ids or self.group_ids or self.profile_id)

    def _explicit_hidden_ids(self):
        Rule = self.env['button.access.menu.rule'].sudo()
        domain = [('active', '=', True)]
        parts = []
        if self.user_ids:
            parts.append(('user_ids', 'in', self.user_ids.ids))
        if self.group_ids:
            parts.append(('group_ids', 'in', self.group_ids.ids))
        if self.profile_id:
            if self.profile_id.hidden_menu_ids:
                return set(self.profile_id.hidden_menu_ids.ids)
            if self.profile_id.generated_group_id:
                parts.append(('group_ids', 'in', [self.profile_id.generated_group_id.id]))
        if not parts:
            return set()
        if len(parts) == 1:
            domain.append(parts[0])
        else:
            domain = domain + ['|'] * (len(parts) - 1) + parts
        return set(Rule.search(domain).mapped('menu_id').ids)

    def _build_app_lines(self):
        hidden = self._explicit_hidden_ids()
        rows = []
        for app in self.env['button.access.menu.rule'].get_installed_home_apps():
            rows.append((0, 0, {
                'menu_id': app['menu_id'],
                'complete_name': app['name'],
                'depth': 0,
                'hide': app['menu_id'] in hidden,
                'is_root': True,
                'xmlid': app['xmlid'],
                'has_action': False,
                'module_name': app['module_name'],
                'module_shortdesc': app['module_shortdesc'] or app['module_name'],
                'is_application': app['is_application'],
                'web_icon_data': app['web_icon_data'],
                'child_count': app['child_count'],
            }))
        return rows

    def _build_tree_lines(self):
        if not self.app_menu_id:
            return []
        Menu = self.env['ir.ui.menu'].with_context(
            {'ir.ui.menu.full_list': True, 'active_test': False})
        menus = Menu.search(
            [('id', 'child_of', self.app_menu_id.id)],
            order='parent_path, sequence, id')
        xmlids = menus._get_menuitems_xmlids()
        hidden = self._explicit_hidden_ids()
        parent_hidden = set()
        rows = []
        for menu in menus:
            depth = (menu.parent_path or '').count('/') - 1
            if depth < 0:
                depth = 0
            is_root = not menu.parent_id or menu.id == self.app_menu_id.id
            by_parent = bool(menu.parent_id and (
                menu.parent_id.id in hidden or menu.parent_id.id in parent_hidden))
            hide = menu.id in hidden or by_parent
            if hide:
                parent_hidden.add(menu.id)
            rows.append((0, 0, {
                'menu_id': menu.id,
                'complete_name': menu.complete_name or menu.name,
                'depth': depth,
                'hide': hide,
                'is_root': is_root,
                'xmlid': xmlids.get(menu.id, '') or '',
                'has_action': bool(menu.action),
                'module_name': (xmlids.get(menu.id) or 'custom').split('.')[0],
                'child_count': Menu.search_count([('parent_id', '=', menu.id)]),
            }))
        return rows

    def _rebuild_lines(self):
        self.line_ids.unlink()
        commands = self._build_tree_lines() if self.app_menu_id else self._build_app_lines()
        self.line_ids = commands

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wiz = self.new(res)
        if 'line_ids' in fields_list:
            res['line_ids'] = (
                wiz._build_tree_lines() if wiz.app_menu_id else wiz._build_app_lines()
            )
        return res

    @api.onchange('app_menu_id', 'user_ids', 'group_ids', 'profile_id')
    def _onchange_reload_lines(self):
        self.line_ids = [(5, 0, 0)] + (
            self._build_tree_lines() if self.app_menu_id else self._build_app_lines()
        )

    def action_reload_apps(self):
        self.ensure_one()
        self.app_menu_id = False
        self._rebuild_lines()
        return self._reopen()

    def action_hide_all(self):
        self.ensure_one()
        self.line_ids.write({'hide': True})
        return self._reopen()

    def action_show_all(self):
        self.ensure_one()
        self.line_ids.write({'hide': False})
        return self._reopen()

    def action_apply(self):
        self.ensure_one()
        if not self._target_ok():
            raise UserError(_('Select at least one user, group, or access profile.'))
        user_ids = [uid for uid in self.user_ids.ids if uid != 1]
        group_ids = list(self.group_ids.ids)
        if self.profile_id:
            group = self.profile_id._ensure_generated_group()
            if group.id not in group_ids:
                group_ids.append(group.id)
        Rule = self.env['button.access.menu.rule'].sudo()
        explicit_hide = []
        explicit_show = []
        for line in self.line_ids:
            if line.hidden_by_parent:
                continue
            if line.hide:
                explicit_hide.append(line.menu_id.id)
            else:
                explicit_show.append(line.menu_id.id)
        if self.profile_id:
            keep = set(self.profile_id.hidden_menu_ids.ids)
            if self.app_menu_id:
                tree_ids = set(self.env['ir.ui.menu'].with_context(
                    {'ir.ui.menu.full_list': True, 'active_test': False}
                ).search([('id', 'child_of', self.app_menu_id.id)]).ids)
                keep -= tree_ids
            else:
                keep -= set(self.line_ids.mapped('menu_id').ids)
            keep |= set(explicit_hide)
            keep -= set(explicit_show)
            self.profile_id.with_context(access_profile_skip_sync=True).write({
                'hidden_menu_ids': [(6, 0, list(keep))],
            })
            self.profile_id._sync_generated()
        else:
            for menu_id in explicit_hide:
                Rule._create_or_update_menu_rule(
                    menu_id, user_ids=user_ids, group_ids=group_ids)
            for menu_id in explicit_show:
                for uid in user_ids:
                    Rule._remove_user_from_menu_rule(menu_id, uid)
                for gid in group_ids:
                    Rule._remove_group_from_menu_rule(menu_id, gid)
        return {'type': 'ir.actions.act_window_close'}

    def action_preview(self):
        self.ensure_one()
        user = self.user_ids[:1]
        if not user and self.group_ids:
            user = self.group_ids[:1].users.filtered(lambda u: u.id != 1)[:1]
        if not user and self.profile_id:
            user = self.profile_id._assigned_users()[:1]
        if not user:
            raise UserError(_('Select a user (or a group/profile with a user) to preview.'))
        Menu = self.env['ir.ui.menu']
        try:
            data = Menu.with_user(user).load_menus(False)
        except Exception:
            data = {}
        root = data.get('root') or {}
        names = []
        for app_id in root.get('children') or []:
            app = data.get(app_id) or {}
            names.append(app.get('name') or '')
            for child_id in (app.get('children') or [])[:12]:
                child = data.get(child_id) or {}
                names.append('    %s' % (child.get('name') or ''))
        self.preview_text = _(
            'Preview as %(user)s (remaining home apps):\n%(apps)s',
            user=user.name,
            apps='\n'.join(names) or _('(none)'),
        )
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Hide Apps & Menus'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class ButtonAccessMenuWizardLine(models.TransientModel):
    _name = 'button.access.menu.wizard.line'
    _description = 'Hide Apps & Menus Line'
    _order = 'id'

    wizard_id = fields.Many2one(
        'button.access.menu.wizard', required=True, ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', required=True, ondelete='cascade')
    complete_name = fields.Char()
    display_label = fields.Char(compute='_compute_display_label')
    depth = fields.Integer()
    hide = fields.Boolean(string='Hide')
    is_root = fields.Boolean()
    xmlid = fields.Char()
    has_action = fields.Boolean()
    hidden_by_parent = fields.Boolean(compute='_compute_hidden_by_parent')
    module_name = fields.Char()
    module_shortdesc = fields.Char()
    is_application = fields.Boolean()
    web_icon_data = fields.Binary()
    child_count = fields.Integer()

    @api.depends('complete_name', 'depth', 'menu_id')
    def _compute_display_label(self):
        for line in self:
            name = line.complete_name or line.menu_id.name or ''
            line.display_label = ('%s%s' % ('\u00a0\u00a0' * max(line.depth, 0), name))

    @api.depends('wizard_id.line_ids.hide', 'wizard_id.line_ids.menu_id', 'menu_id', 'is_root')
    def _compute_hidden_by_parent(self):
        for line in self:
            by_parent = False
            parent = line.menu_id.parent_id
            lines = line.wizard_id.line_ids
            while parent:
                pline = lines.filtered(lambda l, p=parent: l.menu_id.id == p.id)
                if pline and pline[:1].hide:
                    by_parent = True
                    break
                parent = parent.parent_id
            line.hidden_by_parent = by_parent

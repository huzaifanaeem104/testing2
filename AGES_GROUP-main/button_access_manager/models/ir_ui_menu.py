# -*- coding: utf-8 -*-
from odoo import api, models, tools


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _bam_menu_hide_token(self):
        if 'button.access.menu.rule' not in self.env:
            return '0'
        return self.env['button.access.menu.rule']._menu_hide_cache_token()

    @api.model
    @tools.ormcache(
        'self.env.uid',
        'frozenset(self.env.user.groups_id.ids)',
        'debug',
        'self._bam_menu_hide_token()',
    )
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug=debug)
        if self.env.uid == 1 or 'button.access.menu.rule' not in self.env:
            return visible
        hidden = self.env['button.access.menu.rule'].hidden_menu_ids_expanded_for_uid(
            self.env.uid)
        if not hidden:
            return visible
        return visible - hidden

    def _load_menus_blacklist(self):
        ids = super()._load_menus_blacklist()
        if self.env.uid == 1 or 'button.access.menu.rule' not in self.env:
            return ids
        hidden = self.env['button.access.menu.rule'].hidden_menu_ids_expanded_for_uid(
            self.env.uid)
        if not hidden:
            return ids
        return list(set(ids) | hidden)

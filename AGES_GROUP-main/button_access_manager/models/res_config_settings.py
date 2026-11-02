# -*- coding: utf-8 -*-
from odoo import fields, models

from .constants import extra_allowlist, extra_protected_menus


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    button_access_extra_allowlist = fields.Char(
        string='Extra allowlisted models',
        config_parameter='button_access_manager.extra_allowlist',
        help='Comma-separated technical model names. Global New / Delete / '
             'Duplicate rules skip these (same as chatter and other framework models).')

    button_access_protected_menu_xmlids = fields.Char(
        string='Extra protected menus',
        config_parameter='button_access_manager.protected_menu_xmlids',
        help='Comma-separated menu xmlids that cannot be hidden from a Settings '
             'administrator (in addition to Settings, Apps, Users, Access Profiles).')

    def set_values(self):
        super().set_values()
        cache = getattr(self.env.cr, '_button_access_extra_allowlist', None)
        if cache is not None:
            delattr(self.env.cr, '_button_access_extra_allowlist')
        extra_allowlist(self.env)
        extra = getattr(self.env.cr, '_button_access_extra_protected_menus', None)
        if extra is not None:
            delattr(self.env.cr, '_button_access_extra_protected_menus')
        extra_protected_menus(self.env)

# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        uid = self.env.uid
        if not uid or uid == 1:
            result['button_access_rules'] = []
            result['button_access_exceptions'] = []
            result['button_access_hidden_menu_ids'] = []
            return result
        if 'button.access.rule' in self.env:
            Rule = self.env['button.access.rule'].sudo()
            result['button_access_rules'] = Rule.get_rules_for_current_user()
            result['button_access_exceptions'] = Rule.get_exceptions_for_current_user()
        else:
            result['button_access_rules'] = []
            result['button_access_exceptions'] = []
        if 'button.access.menu.rule' in self.env:
            MenuRule = self.env['button.access.menu.rule'].sudo()
            result['button_access_hidden_menu_ids'] = list(
                MenuRule.hidden_menu_ids_expanded_for_uid(uid))
        else:
            result['button_access_hidden_menu_ids'] = []
        return result

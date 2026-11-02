# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.web.controllers.action import Action

    class ButtonAccessAction(Action):

        def _resolve_action_record(self, action_id):
            Actions = request.env['ir.actions.actions'].sudo()
            try:
                numeric_id = int(action_id)
            except (TypeError, ValueError):
                numeric_id = None
            action = Actions.browse()
            if numeric_id:
                action = Actions.browse([numeric_id])
            elif isinstance(action_id, str) and '.' in action_id:
                try:
                    action = request.env.ref(action_id)
                except Exception:
                    action = Actions.browse()
            elif isinstance(action_id, str) and action_id:
                action = Actions.search([('path', '=', action_id)], limit=1)
            if not action:
                return action
            action_type = action.type
            if action_type and action_type in request.env:
                return request.env[action_type].sudo().browse(action.id)
            return action

        def _enforce_loaded_action(self, action_id):
            if not request.env.uid or request.env.uid == 1:
                return
            try:
                action = self._resolve_action_record(action_id)
            except Exception:
                _logger.exception(
                    'button_access_manager: could not resolve action %s', action_id)
                return
            if not action:
                return
            if 'button.access.rule' in request.env:
                request.env['button.access.rule'].sudo().enforce_action_record(action)
            if 'button.access.menu.rule' in request.env:
                request.env['button.access.menu.rule'].sudo().enforce_action(action)

        @http.route()
        def load(self, action_id, context=None):
            self._enforce_loaded_action(action_id)
            return super().load(action_id, context=context)

        @http.route()
        def run(self, action_id, context=None):
            self._enforce_loaded_action(action_id)
            return super().run(action_id, context=context)

except ImportError:
    _logger.warning(
        'button_access_manager: could not locate web.controllers.action.Action, '
        'HTTP action/report enforcement is disabled.')

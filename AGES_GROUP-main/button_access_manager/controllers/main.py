# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

from odoo.addons.button_access_manager.models.constants import (
    ARCHIVE_METHODS,
    METHOD_TO_BUTTON_TYPE,
)

_logger = logging.getLogger(__name__)

OBJECT_KW_PREFIXES = ('action_', 'button_')


def _enforce(model, button_type, technical_name=''):
    if not request.env.uid or 'button.access.rule' not in request.env:
        return
    request.env['button.access.rule'].sudo().enforce(model, button_type, technical_name)


def _ids_empty(args):
    if not args:
        return True
    ids = args[0]
    return not ids


try:
    from odoo.addons.web.controllers.dataset import DataSet

    class ButtonAccessDataSet(DataSet):
        """Blocks create / delete / duplicate / export / object-methods at the
        HTTP boundary. ORM overrides on `base` are the second layer.
        """

        @http.route()
        def call_kw(self, model, method, args, kwargs, path=None):
            if request.env.uid:
                button_type = METHOD_TO_BUTTON_TYPE.get(method)
                if method == 'web_save' and _ids_empty(args):
                    _enforce(model, 'create')
                elif button_type:
                    _enforce(model, button_type)
                elif method in ARCHIVE_METHODS or method.startswith(OBJECT_KW_PREFIXES):
                    _enforce(model, 'object', method)
            return super().call_kw(model, method, args, kwargs, path=path)

        @http.route()
        def call_button(self, model, method, args, kwargs, path=None):
            if request.env.uid:
                _enforce(model, 'object', method)
            return super().call_button(model, method, args, kwargs, path=path)

except ImportError:
    _logger.warning(
        'button_access_manager: could not locate web.controllers.dataset.DataSet, '
        'HTTP call_kw/call_button enforcement is disabled.')


class ButtonAccessRulesController(http.Controller):

    @http.route('/button_access_manager/rules', type='json', auth='user')
    def get_rules(self):
        if request.env.uid == 1 or 'button.access.rule' not in request.env:
            return []
        return request.env['button.access.rule'].sudo().get_rules_for_current_user()

# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    from werkzeug.datastructures import FileStorage
    from odoo.addons.web.controllers.pivot import TableExporter

    class ButtonAccessTableExporter(TableExporter):

        @http.route('/web/pivot/export_xlsx', type='http', auth='user', readonly=True)
        def export_xlsx(self, data, **kw):
            try:
                if isinstance(data, FileStorage):
                    raw = data.stream.read()
                    try:
                        data.stream.seek(0)
                    except Exception:
                        pass
                    jdata = json.loads(raw or b'{}')
                else:
                    jdata = json.loads(data) if data else {}
                model = jdata.get('model')
                if model:
                    request.env['button.access.rule'].sudo().enforce(model, 'export')
            except AccessError:
                raise
            except Exception:
                _logger.exception(
                    'button_access_manager: pivot export guard failed, denying export.')
                request.env['button.access.rule'].sudo().enforce('', 'export')
            return super().export_xlsx(data, **kw)

except ImportError:
    _logger.warning(
        'button_access_manager: could not locate web.controllers.pivot, '
        'HTTP pivot export enforcement is disabled.')

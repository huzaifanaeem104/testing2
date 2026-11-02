# -*- coding: utf-8 -*-
import json
import logging

from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.web.controllers.export import CSVExport, ExcelExport

    def _enforce_export(data):
        params = json.loads(data) if isinstance(data, (bytes, str)) else data
        model = params.get('model')
        if model and request.env.uid:
            request.env['button.access.rule'].sudo().enforce(model, 'export')

    class ButtonAccessExcelExport(ExcelExport):
        def base(self, data):
            try:
                _enforce_export(data)
            except AccessError:
                raise
            except Exception:
                _logger.exception('button_access_manager: export guard failed, denying export.')
                request.env['button.access.rule'].sudo().enforce(
                    json.loads(data).get('model') if isinstance(data, (bytes, str)) else '',
                    'export',
                )
            return super().base(data)

    class ButtonAccessCSVExport(CSVExport):
        def base(self, data):
            try:
                _enforce_export(data)
            except AccessError:
                raise
            except Exception:
                _logger.exception('button_access_manager: export guard failed, denying export.')
                request.env['button.access.rule'].sudo().enforce(
                    json.loads(data).get('model') if isinstance(data, (bytes, str)) else '',
                    'export',
                )
            return super().base(data)

except ImportError:
    _logger.warning(
        'button_access_manager: could not locate web.controllers.export, '
        'HTTP export enforcement is disabled (export_data ORM hook still applies).')

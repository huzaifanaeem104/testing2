# -*- coding: utf-8 -*-
import logging

from odoo import models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class BaseImportImport(models.TransientModel):
    """Blocks the Import action server-side for restricted users."""
    _inherit = 'base_import.import'

    def execute_import(self, fields, columns, options, dryrun=False):
        try:
            if not dryrun and self.res_model:
                self.env['button.access.rule'].sudo().enforce(self.res_model, 'import')
        except AccessError:
            raise
        except Exception:
            _logger.exception('button_access_manager: import guard failed, denying import.')
            raise AccessError(
                self.env._(
                    "This action has been restricted for your user account. "
                    "Please contact your administrator if you believe this is a mistake."
                )
            )
        return super().execute_import(fields, columns, options, dryrun=dryrun)

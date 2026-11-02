# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models


class HrWorkEntryRegenerationWizard(models.TransientModel):
    _inherit = 'hr.work.entry.regeneration.wizard'

    def _work_entry_fields_to_nullify(self):
        fields_list = super()._work_entry_fields_to_nullify()
        return fields_list + ['attendance_id']

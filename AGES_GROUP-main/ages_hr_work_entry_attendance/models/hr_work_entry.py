# -*- coding: utf-8 -*-
# Copyright AGES Group
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    attendance_id = fields.Many2one(
        comodel_name='hr.attendance',
        string='Attendance',
        index=True,
        ondelete='set null',
    )

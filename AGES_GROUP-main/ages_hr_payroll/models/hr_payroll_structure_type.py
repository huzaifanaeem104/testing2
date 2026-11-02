# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char('Structure Type', required=True)
    default_schedule_pay = fields.Selection([
        ('annually', 'Annually'),
        ('semi-annually', 'Semi-annually'),
        ('quarterly', 'Quarterly'),
        ('bi-monthly', 'Bi-monthly'),
        ('monthly', 'Monthly'),
        ('semi-monthly', 'Semi-monthly'),
        ('bi-weekly', 'Bi-weekly'),
        ('weekly', 'Weekly'),
        ('daily', 'Daily'),
    ], string='Default Scheduled Pay', default='monthly')
    struct_ids = fields.One2many('hr.payroll.structure', 'type_id', string="Structures")
    default_struct_id = fields.Many2one('hr.payroll.structure', string="Regular Pay Structure")
    default_work_entry_type_id = fields.Many2one(
        'hr.work.entry.type',
        help="Work entry type for regular attendances.",
        default=lambda self: self.env.ref('hr_work_entry.work_entry_type_attendance', raise_if_not_found=False),
        required=False,
    )
    wage_type = fields.Selection([
        ('monthly', 'Fixed Wage'),
        ('hourly', 'Hourly Wage'),
        ('daily', 'Daily Wage'),
    ], string="Default Wage Type", default='monthly', required=True)
    struct_type_count = fields.Integer(compute='_compute_struct_type_count')

    def _compute_struct_type_count(self):
        for structure_type in self:
            structure_type.struct_type_count = len(structure_type.struct_ids)

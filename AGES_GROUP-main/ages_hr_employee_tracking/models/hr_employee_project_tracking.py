# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeProjectTracking(models.Model):
    _name = 'hr.employee.project.tracking'
    _description = 'Employee Project Tracking'
    _order = 'date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    old_project_id = fields.Many2one(
        'project.project',
        string='Old Project',
        readonly=True,
    )
    new_project_id = fields.Many2one(
        'project.project',
        string='New Project',
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        readonly=True,
        help='User responsible for that change',
    )

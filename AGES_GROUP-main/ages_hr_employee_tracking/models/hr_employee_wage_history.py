# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeWageHistory(models.Model):
    _name = 'hr.employee.wage.history'
    _description = 'Employee Wage History'
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
    currency_id = fields.Many2one(
        'res.currency',
        related='employee_id.company_id.currency_id',
        string='Currency',
        readonly=True,
    )
    old_wage = fields.Monetary(
        string='Old Wage',
        currency_field='currency_id',
        readonly=True,
    )
    new_wage = fields.Monetary(
        string='New Wage',
        currency_field='currency_id',
        readonly=True,
    )
    difference = fields.Monetary(
        string='Difference',
        currency_field='currency_id',
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        readonly=True,
        help='User responsible for that change',
    )

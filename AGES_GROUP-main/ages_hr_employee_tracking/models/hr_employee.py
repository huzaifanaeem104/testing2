# -*- coding: utf-8 -*-
from odoo import fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ages_employee_category = fields.Selection([
        ('staff', 'Employee-Staff'),
        ('site', 'Employee-Site'),
        ('labor', 'Labor-Site'),
    ], string='Category', required=True, default='staff', tracking=True)

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        tracking=True,
    )
    wage = fields.Monetary(
        string='Wage',
        currency_field='currency_id',
        tracking=True,
    )
    hourly_wage = fields.Monetary(
        string='Hourly Wage',
        currency_field='currency_id',
        tracking=True,
    )
    project_tracking_ids = fields.One2many(
        'hr.employee.project.tracking',
        'employee_id',
        string='Project Tracking History',
    )
    wage_history_ids = fields.One2many(
        'hr.employee.wage.history',
        'employee_id',
        string='Wage History',
    )

    def action_open_transfer_wizard(self):
        self.ensure_one()
        return {
            'name': _('Employee Transfer & Wage Change'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.id,
                'default_job_id': self.job_id.id if self.job_id else False,
                'default_old_project_id': self.project_id.id if self.project_id else False,
            },
        }

    def action_open_bulk_transfer_wizard(self):
        employees = self or self.browse(self.env.context.get('active_ids', []))
        if not employees:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'name': _('Bulk Transfer Project'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.bulk.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_ids': [(6, 0, employees.ids)],
                'active_ids': employees.ids,
                'active_model': 'hr.employee',
            },
        }

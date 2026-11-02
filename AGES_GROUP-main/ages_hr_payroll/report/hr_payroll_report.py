# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class HrPayrollReport(models.Model):
    _name = 'hr.payroll.report'
    _description = 'Payroll Analysis'
    _auto = False
    _order = 'date_from desc'

    employee_id = fields.Many2one('hr.employee', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    job_id = fields.Many2one('hr.job', readonly=True)
    contract_id = fields.Many2one('hr.contract', readonly=True)
    struct_id = fields.Many2one('hr.payroll.structure', readonly=True)
    date_from = fields.Date(readonly=True)
    date_to = fields.Date(readonly=True)
    count = fields.Integer(readonly=True)
    net_wage = fields.Float(readonly=True)
    basic_wage = fields.Float(readonly=True)
    gross_wage = fields.Float(readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('paid', 'Paid'),
        ('cancel', 'Canceled'),
    ], readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    p.id AS id,
                    p.employee_id,
                    p.company_id,
                    p.department_id,
                    p.job_id,
                    p.contract_id,
                    p.struct_id,
                    p.date_from,
                    p.date_to,
                    p.state,
                    1 AS count,
                    p.net_wage,
                    p.basic_wage,
                    p.gross_wage
                FROM hr_payslip p
                WHERE p.state != 'cancel'
            )
        """ % self._table)

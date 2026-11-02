# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class HrWorkEntryReport(models.Model):
    _name = 'hr.work.entry.report'
    _description = 'Work Entries Analysis'
    _auto = False

    employee_id = fields.Many2one('hr.employee', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    work_entry_type_id = fields.Many2one('hr.work.entry.type', readonly=True)
    contract_id = fields.Many2one('hr.contract', readonly=True)
    date_start = fields.Datetime(readonly=True)
    duration = fields.Float(readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('conflict', 'Conflict'),
    ], readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    we.id AS id,
                    we.employee_id,
                    we.company_id,
                    we.work_entry_type_id,
                    we.contract_id,
                    we.date_start,
                    we.duration,
                    we.state
                FROM hr_work_entry we
            )
        """ % self._table)

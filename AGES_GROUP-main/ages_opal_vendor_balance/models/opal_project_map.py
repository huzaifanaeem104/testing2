# -*- coding: utf-8 -*-

from odoo import api, fields, models


class OpalProjectMap(models.Model):
    _name = 'opal.project.map'
    _description = 'OPAL project code to Odoo project map'
    _order = 'project_code'

    project_code = fields.Char(required=True, index=True)
    project_name = fields.Char()
    project_id = fields.Many2one(
        'project.project',
        ondelete='set null',
        index=True,
    )

    _sql_constraints = [
        ('project_code_uniq', 'unique(project_code)', 'Each OPAL project code can be mapped once.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_line_projects()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'project_code', 'project_id'} & set(vals):
            self._sync_line_projects()
        return result

    def unlink(self):
        codes = self.mapped('project_code')
        result = super().unlink()
        domain = [('project_code', 'in', codes)]
        self.env['opal.vendor.project'].search(domain).write({'project_id': False})
        self.env['opal.vendor.project.account'].search(domain).write({'project_id': False})
        return result

    def _sync_line_projects(self):
        for rec in self:
            project_id = rec.project_id.id if rec.project_id else False
            domain = [('project_code', '=', rec.project_code)]
            self.env['opal.vendor.project'].search(domain).write({'project_id': project_id})
            self.env['opal.vendor.project.account'].search(domain).write({'project_id': project_id})

# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class ages_custom_reports(models.Model):
#     _name = 'ages_custom_reports.ages_custom_reports'
#     _description = 'ages_custom_reports.ages_custom_reports'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100


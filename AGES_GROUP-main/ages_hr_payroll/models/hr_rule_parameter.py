# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class HrRuleParameter(models.Model):
    _name = 'hr.rule.parameter'
    _description = 'Rule Parameter'
    _rec_name = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    country_id = fields.Many2one('res.country')
    parameter_version_ids = fields.One2many('hr.rule.parameter.value', 'rule_parameter_id')

    _sql_constraints = [
        ('code_uniq', 'unique (code)', 'Parameter code must be unique.'),
    ]

    @api.model
    def _get_parameter_from_code(self, code, date=None, raise_if_not_found=True):
        if date is None:
            date = fields.Date.today()
        parameter = self.search([('code', '=', code)], limit=1)
        if not parameter:
            if raise_if_not_found:
                raise UserError(_('No rule parameter with code "%s".', code))
            return None
        value = self.env['hr.rule.parameter.value'].search([
            ('rule_parameter_id', '=', parameter.id),
            ('date_from', '<=', date),
        ], order='date_from desc', limit=1)
        if not value:
            if raise_if_not_found:
                raise UserError(_('No value for rule parameter "%s" on %s.', code, date))
            return None
        return safe_eval(value.parameter_value)


class HrRuleParameterValue(models.Model):
    _name = 'hr.rule.parameter.value'
    _description = 'Rule Parameter Value'
    _order = 'date_from desc'

    rule_parameter_id = fields.Many2one('hr.rule.parameter', required=True, ondelete='cascade')
    code = fields.Char(related='rule_parameter_id.code', store=True)
    country_id = fields.Many2one(related='rule_parameter_id.country_id', store=True)
    date_from = fields.Date(required=True)
    parameter_value = fields.Text(required=True, help="Python literal, e.g. 0.12 or {'a': 1}")

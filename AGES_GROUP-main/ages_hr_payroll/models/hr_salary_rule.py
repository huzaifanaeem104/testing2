# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class HrSalaryRule(models.Model):
    _name = 'hr.salary.rule'
    _order = 'sequence, id'
    _description = 'Salary Rule'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    struct_id = fields.Many2one('hr.payroll.structure', string="Salary Structure", required=True, ondelete='cascade')
    sequence = fields.Integer(required=True, index=True, default=5)
    quantity = fields.Char(default='1.0')
    category_id = fields.Many2one('hr.salary.rule.category', string='Category', required=True)
    active = fields.Boolean(default=True)
    appears_on_payslip = fields.Boolean(string='Appears on Payslip', default=True)
    appears_on_employee_cost_dashboard = fields.Boolean(default=False)
    appears_on_payroll_report = fields.Boolean(default=False)
    condition_select = fields.Selection([
        ('none', 'Always True'),
        ('range', 'Range'),
        ('input', 'Other Input'),
        ('python', 'Python Expression')
    ], string="Condition Based on", default='none', required=True)
    condition_range = fields.Char(string='Range Based on', default='contract.wage')
    condition_other_input_id = fields.Many2one('hr.payslip.input.type', domain=[('is_quantity', '=', False)])
    condition_python = fields.Text(string='Python Condition', required=True, default="result = True")
    condition_range_min = fields.Float(string='Minimum Range')
    condition_range_max = fields.Float(string='Maximum Range')
    amount_select = fields.Selection([
        ('percentage', 'Percentage (%)'),
        ('fix', 'Fixed Amount'),
        ('input', 'Other Input'),
        ('code', 'Python Code'),
    ], string='Amount Type', index=True, required=True, default='fix')
    amount_fix = fields.Float(string='Fixed Amount', digits='Payroll')
    amount_percentage = fields.Float(string='Percentage (%)', digits='Payroll Rate')
    amount_other_input_id = fields.Many2one('hr.payslip.input.type', domain=[('is_quantity', '=', False)])
    amount_python_compute = fields.Text(string='Python Code', default="result = contract.wage")
    amount_percentage_base = fields.Char(string='Percentage based on', default='contract.wage')
    partner_id = fields.Many2one('res.partner', string='Partner')
    note = fields.Html(string='Description', translate=True)

    def _raise_error(self, localdict, error_type, e):
        raise UserError(_(
            "%(error_type)s\n- Employee: %(employee)s\n- Contract: %(contract)s\n"
            "- Payslip: %(payslip)s\n- Salary rule: %(name)s (%(code)s)\n- Error: %(error_message)s",
            error_type=error_type,
            employee=localdict['employee'].name,
            contract=localdict['contract'].name,
            payslip=localdict['payslip'].name,
            name=self.name,
            code=self.code,
            error_message=e,
        ))

    def _compute_rule(self, localdict):
        self.ensure_one()
        localdict['localdict'] = localdict
        if self.amount_select == 'fix':
            try:
                return self.amount_fix or 0.0, float(safe_eval(self.quantity, localdict)), 100.0
            except Exception as e:
                self._raise_error(localdict, _("Wrong quantity defined for:"), e)
        if self.amount_select == 'percentage':
            try:
                return (
                    float(safe_eval(self.amount_percentage_base, localdict)),
                    float(safe_eval(self.quantity, localdict)),
                    self.amount_percentage or 0.0,
                )
            except Exception as e:
                self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e)
        if self.amount_select == 'input':
            if self.amount_other_input_id.code not in localdict['inputs']:
                return 0.0, 1.0, 100.0
            return localdict['inputs'][self.amount_other_input_id.code].amount, 1.0, 100.0
        try:
            safe_eval(self.amount_python_compute or 0.0, localdict, mode='exec', nocopy=True)
            return float(localdict['result']), localdict.get('result_qty', 1.0), localdict.get('result_rate', 100.0)
        except Exception as e:
            self._raise_error(localdict, _("Wrong python code defined for:"), e)

    def _satisfy_condition(self, localdict):
        self.ensure_one()
        localdict['localdict'] = localdict
        if self.condition_select == 'none':
            return True
        if self.condition_select == 'range':
            try:
                result = safe_eval(self.condition_range, localdict)
                return self.condition_range_min <= result <= self.condition_range_max
            except Exception as e:
                self._raise_error(localdict, _("Wrong range condition defined for:"), e)
        if self.condition_select == 'input':
            return self.condition_other_input_id.code in localdict['inputs']
        try:
            safe_eval(self.condition_python, localdict, mode='exec', nocopy=True)
            return localdict.get('result', False)
        except Exception as e:
            self._raise_error(localdict, _("Wrong python condition defined for:"), e)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._("%s (copy)", rule.name)) for rule, vals in zip(self, vals_list)]

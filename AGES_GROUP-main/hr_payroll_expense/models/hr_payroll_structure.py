# -*- coding: utf-8 -*-

from odoo import api, models


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    @api.model_create_multi
    def create(self, vals_list):
        structures = super().create(vals_list)
        structures._ensure_expense_salary_rule()
        return structures

    def _ensure_expense_salary_rule(self):
        category = self.env.ref('ages_hr_payroll.ALW', raise_if_not_found=False)
        input_type = self.env.ref('hr_payroll_expense.expense_other_input', raise_if_not_found=False)
        if not category or not input_type:
            return
        Rule = self.env['hr.salary.rule']
        for structure in self:
            if not structure.rule_ids.filtered(lambda rule: rule.code == 'EXPENSES'):
                Rule.create({
                    'name': 'Expense Reimbursement',
                    'code': 'EXPENSES',
                    'sequence': 95,
                    'category_id': category.id,
                    'struct_id': structure.id,
                    'condition_select': 'input',
                    'condition_other_input_id': input_type.id,
                    'amount_select': 'input',
                    'amount_other_input_id': input_type.id,
                    'appears_on_payslip': True,
                })
            if input_type not in structure.input_line_type_ids:
                structure.input_line_type_ids = [(4, input_type.id)]

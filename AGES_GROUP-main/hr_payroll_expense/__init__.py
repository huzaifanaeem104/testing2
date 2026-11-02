from . import models


def _add_expense_rule_to_structures(env):
    env['hr.payroll.structure'].search([])._ensure_expense_salary_rule()

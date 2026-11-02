# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.tools import float_compare


class HrEmployeeTransferWizard(models.TransientModel):
    _name = 'hr.employee.transfer.wizard'
    _description = 'Employee Transfer & Wage Change Wizard'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        readonly=True,
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        help='Can be changeable, by default shows current job position.',
    )
    old_project_id = fields.Many2one(
        'project.project',
        string='OLD Project',
        readonly=True,
    )
    new_project_id = fields.Many2one(
        'project.project',
        string='New Project',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True,
    )
    # Plain stored fields (NOT computed): readonly computed old_wage was often
    # missing from the create payload and fell back to 0 in wage history.
    old_wage = fields.Monetary(
        string='Old Wage',
        currency_field='currency_id',
        readonly=True,
    )
    new_wage = fields.Monetary(
        string='New Wage',
        currency_field='currency_id',
        help='By default matches Old Wage, but can be changed to update contract wage based on wage type.',
    )

    def _get_employee_contract(self, employee):
        if not employee:
            return self.env['hr.contract']
        if 'contract_id' in employee._fields and employee.contract_id:
            return employee.contract_id
        return self.env['hr.contract'].search(
            [('employee_id', '=', employee.id), ('state', 'in', ('open', 'draft'))],
            order='date_start desc, id desc',
            limit=1,
        ) or self.env['hr.contract'].search(
            [('employee_id', '=', employee.id)],
            order='id desc',
            limit=1,
        )

    def _get_current_wage(self, employee):
        """Read current wage from contract (by wage_type), else employee fields."""
        if not employee:
            return 0.0
        contract = self._get_employee_contract(employee)
        if contract:
            wage_type = getattr(contract, 'wage_type', 'monthly') or 'monthly'
            if wage_type == 'hourly' and 'hourly_wage' in contract._fields:
                return contract.hourly_wage or 0.0
            if wage_type == 'daily' and 'daily_wage' in contract._fields:
                return contract.daily_wage or 0.0
            if 'wage' in contract._fields and contract.wage:
                return contract.wage or 0.0
        # Fallback: wages stored directly on the employee
        if getattr(employee, 'hourly_wage', 0.0):
            return employee.hourly_wage or 0.0
        return getattr(employee, 'wage', 0.0) or 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        employee_id = res.get('employee_id') or self.env.context.get('default_employee_id')
        if employee_id:
            employee = self.env['hr.employee'].browse(employee_id)
            wage = self._get_current_wage(employee)
            if 'currency_id' in fields_list or not fields_list:
                res['currency_id'] = (
                    employee.company_id.currency_id.id
                    or self.env.company.currency_id.id
                )
            if 'old_wage' in fields_list or not fields_list:
                res['old_wage'] = wage
            if 'new_wage' in fields_list or not fields_list:
                res['new_wage'] = wage
            if 'job_id' in fields_list and not res.get('job_id'):
                res['job_id'] = employee.job_id.id
            if 'old_project_id' in fields_list and not res.get('old_project_id'):
                res['old_project_id'] = employee.project_id.id
        return res

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if not self.employee_id:
            self.old_wage = 0.0
            self.new_wage = 0.0
            self.currency_id = False
            return
        wage = self._get_current_wage(self.employee_id)
        self.currency_id = (
            self.employee_id.company_id.currency_id
            or self.env.company.currency_id
        )
        self.old_wage = wage
        self.new_wage = wage
        if not self.job_id:
            self.job_id = self.employee_id.job_id
        if not self.old_project_id:
            self.old_project_id = self.employee_id.project_id

    def action_apply_transfer(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return {'type': 'ir.actions.act_window_close'}

        # Snapshot old wage before any writes (never trust a recomputed 0)
        old_wage = self.old_wage
        if not old_wage:
            old_wage = self._get_current_wage(employee)

        # 1. Update Job Position
        if self.job_id and employee.job_id != self.job_id:
            employee.job_id = self.job_id.id
            contract = self._get_employee_contract(employee)
            if contract and 'job_id' in contract._fields:
                contract.job_id = self.job_id.id

        # 2. Update Project & Log Project Tracking
        if self.new_project_id and employee.project_id != self.new_project_id:
            old_proj = employee.project_id
            new_proj = self.new_project_id
            employee.project_id = new_proj.id
            contract = self._get_employee_contract(employee)
            if contract and 'project_id' in contract._fields:
                contract.project_id = new_proj.id

            self.env['hr.employee.project.tracking'].create({
                'employee_id': employee.id,
                'date': fields.Datetime.now(),
                'old_project_id': old_proj.id if old_proj else False,
                'new_project_id': new_proj.id,
                'user_id': self.env.user.id,
            })

        # 3. Update Wage on Contract & Employee + log Wage History
        currency = self.currency_id or employee.company_id.currency_id or self.env.company.currency_id
        prec = currency.decimal_places or 2
        if float_compare(self.new_wage, old_wage, precision_digits=prec) != 0:
            diff = self.new_wage - old_wage
            contract = self._get_employee_contract(employee)
            if contract:
                wage_type = getattr(contract, 'wage_type', 'monthly') or 'monthly'
                if wage_type == 'hourly' and 'hourly_wage' in contract._fields:
                    contract.hourly_wage = self.new_wage
                    if 'hourly_wage' in employee._fields:
                        employee.hourly_wage = self.new_wage
                elif wage_type == 'daily' and 'daily_wage' in contract._fields:
                    contract.daily_wage = self.new_wage
                    if 'wage' in employee._fields:
                        employee.wage = self.new_wage
                else:
                    contract.wage = self.new_wage
                    if 'wage' in employee._fields:
                        employee.wage = self.new_wage
            else:
                if 'wage' in employee._fields:
                    employee.wage = self.new_wage

            self.env['hr.employee.wage.history'].create({
                'employee_id': employee.id,
                'date': fields.Datetime.now(),
                'old_wage': old_wage,
                'new_wage': self.new_wage,
                'difference': diff,
                'user_id': self.env.user.id,
            })

        return {'type': 'ir.actions.act_window_close'}


class HrEmployeeBulkTransferWizard(models.TransientModel):
    _name = 'hr.employee.bulk.transfer.wizard'
    _description = 'Bulk Employee Project Transfer Wizard'

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        required=True,
        readonly=True,
    )
    new_project_id = fields.Many2one(
        'project.project',
        string='New Project',
        required=True,
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        help='Optional. If set, applied to all selected employees.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        if active_ids and ('employee_ids' in fields_list or not fields_list):
            res['employee_ids'] = [(6, 0, active_ids)]
        return res

    def action_apply_bulk_transfer(self):
        self.ensure_one()
        if not self.employee_ids:
            return {'type': 'ir.actions.act_window_close'}
        if not self.new_project_id:
            return {'type': 'ir.actions.act_window_close'}

        Tracking = self.env['hr.employee.project.tracking']
        for employee in self.employee_ids:
            if self.job_id and employee.job_id != self.job_id:
                employee.job_id = self.job_id.id
                if 'contract_id' in employee._fields and employee.contract_id:
                    employee.contract_id.job_id = self.job_id.id

            if employee.project_id == self.new_project_id:
                continue

            old_proj = employee.project_id
            employee.project_id = self.new_project_id.id
            if 'contract_id' in employee._fields and employee.contract_id \
                    and 'project_id' in employee.contract_id._fields:
                employee.contract_id.project_id = self.new_project_id.id

            Tracking.create({
                'employee_id': employee.id,
                'date': fields.Datetime.now(),
                'old_project_id': old_proj.id if old_proj else False,
                'new_project_id': self.new_project_id.id,
                'user_id': self.env.user.id,
            })

        return {'type': 'ir.actions.act_window_close'}

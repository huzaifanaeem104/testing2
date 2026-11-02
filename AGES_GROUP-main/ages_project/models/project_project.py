# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    allow_billable = fields.Boolean(default=True)
    ages_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Project Location',
        copy=False,
    )
    ages_sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        tracking=True,
        help='Sub companies defined in Accounting → Configuration → Sub Companies.',
    )
    ages_contract_ids = fields.One2many(
        comodel_name='ages.contract',
        inverse_name='project_id',
        string='Contracts',
    )
    ages_contract_count = fields.Integer(
        string='Contracts Count',
        compute='_compute_ages_contract_count',
    )
    running_bill_count = fields.Integer(
        string='Running Bills Count',
        compute='_compute_ages_project_stat_counts',
    )
    mobilization_count = fields.Integer(
        string='Mobilization Count',
        compute='_compute_ages_project_stat_counts',
    )
    retention_count = fields.Integer(
        string='Retention Count',
        compute='_compute_ages_project_stat_counts',
    )

    @api.depends('ages_contract_ids')
    def _compute_ages_contract_count(self):
        for project in self:
            project.ages_contract_count = len(project.ages_contract_ids)

    def _compute_ages_project_stat_counts(self):
        for project in self:
            if 'ages.running.bill' in self.env:
                project.running_bill_count = self.env['ages.running.bill'].search_count([('project_id', '=', project.id)])
            else:
                project.running_bill_count = 0
            if 'ages.mobilization.advance' in self.env:
                project.mobilization_count = self.env['ages.mobilization.advance'].search_count([('project_id', '=', project.id)])
            else:
                project.mobilization_count = 0
            if 'ages.retention.recovery' in self.env:
                project.retention_count = self.env['ages.retention.recovery'].search_count([('project_id', '=', project.id)])
            else:
                project.retention_count = 0

    @api.onchange('ages_sub_company_id')
    def _onchange_ages_sub_company_id(self):
        if self.ages_sub_company_id.company_id:
            self.company_id = self.ages_sub_company_id.company_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('allow_billable', True)
        projects = super().create(vals_list)
        if not self.env.context.get('ages_skip_auto_setup'):
            projects._ages_create_location_and_analytic()
        return projects

    def _ages_get_analytic_plan(self):
        """Use the official Project analytic plan, then company default."""
        self.ensure_one()
        try:
            project_plan, _other_plans = self.env['account.analytic.plan']._get_all_plans()
            if project_plan:
                return project_plan
        except UserError:
            project_plan = self.env['account.analytic.plan']
        company = self.company_id or self.env.company
        if company.ages_default_analytic_plan_id:
            return company.ages_default_analytic_plan_id
        plan = self.env['account.analytic.plan'].search([('name', '=', 'Project')], limit=1)
        if plan:
            return plan
        raise UserError(_(
            "Please set a Project analytic plan (or Default Analytic Plans in "
            "Project → Configuration → Settings) before creating a project."
        ))

    def _ages_create_location_and_analytic(self):
        Location = self.env['stock.location'].sudo()
        Analytic = self.env['account.analytic.account'].sudo()
        for project in self:
            company = project.company_id or self.env.company
            analytic = project.account_id
            if not analytic:
                plan = project._ages_get_analytic_plan()
                analytic = Analytic.create({
                    'name': project.name,
                    'plan_id': plan.id,
                    'partner_id': project.partner_id.id,
                    'company_id': company.id,
                    'ages_project_id': project.id,
                })
                project.account_id = analytic.id

            location = project.ages_location_id
            if not location:
                parent = company.ages_default_parent_location_id
                if not parent:
                    raise UserError(_(
                        'Please set Default Parent Location in Project → Configuration → Settings '
                        'before creating a project.'
                    ))
                location = Location.create({
                    'name': project.name,
                    'usage': 'internal',
                    'location_id': parent.id,
                    'company_id': company.id,
                    'ages_project_id': project.id,
                    'ages_analytic_account_id': analytic.id,
                })
                project.ages_location_id = location.id

            analytic_vals = {
                'ages_project_id': project.id,
                'ages_location_id': location.id,
            }
            if project.ages_contract_id:
                analytic_vals['ages_contract_id'] = project.ages_contract_id.id
            analytic.write(analytic_vals)
            location.write({
                'ages_project_id': project.id,
                'ages_analytic_account_id': analytic.id,
                'ages_contract_id': project.ages_contract_id.id if project.ages_contract_id else False,
            })

    def _get_stat_buttons(self):
        buttons = super()._get_stat_buttons()
        return [button for button in buttons if button.get('action') != 'action_view_sos']

    def action_open_project_form(self):
        """Open the full project form after the create wizard saves."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.project',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('project.edit_project').id, 'form')],
            'target': 'current',
        }

    def action_create_contract(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Client is required before creating a contract.'))
        if not self.ages_sub_company_id:
            raise UserError(_('Active Company is required before creating a contract.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Contract'),
            'res_model': 'ages.contract',
            'view_mode': 'form',
            'view_id': self.env.ref('ages_contracts.view_ages_contract_form').id,
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_date_start': self.date_start,
                'default_date_close': self.date,
                'default_project_id': self.id,
                'default_analytic_account_id': self.account_id.id,
                'default_location_id': self.ages_location_id.id,
                'default_sub_company_id': self.ages_sub_company_id.id,
                'default_company_id': self.company_id.id,
            },
        }

    def action_view_contracts(self):
        self.ensure_one()
        contracts = self.ages_contract_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Contracts'),
            'res_model': 'ages.contract',
            'target': 'current',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_sub_company_id': self.ages_sub_company_id.id,
                'default_company_id': self.company_id.id,
            },
        }
        form_view = self.env.ref('ages_contracts.view_ages_contract_form')
        if len(contracts) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': contracts.id,
                'views': [(form_view.id, 'form')],
            })
        else:
            list_view = self.env.ref('ages_contracts.view_ages_contract_list')
            action.update({
                'view_mode': 'list,form',
                'views': [(list_view.id, 'list'), (form_view.id, 'form')],
            })
        return action

    def action_view_running_bills(self):
        self.ensure_one()
        bills = self.env['ages.running.bill'].search([('project_id', '=', self.id)])
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Running Bills'),
            'res_model': 'ages.running.bill',
            'target': 'current',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_sub_company_id': self.ages_sub_company_id.id if 'ages_sub_company_id' in self._fields else False,
                'default_company_id': self.company_id.id,
            },
        }
        form_view = self.env.ref('ages_running_bills.view_ages_running_bill_form', raise_if_not_found=False)
        list_view = self.env.ref('ages_running_bills.view_ages_running_bill_list', raise_if_not_found=False)
        if len(bills) == 1 and form_view:
            action.update({
                'view_mode': 'form',
                'res_id': bills.id,
                'views': [(form_view.id, 'form')],
            })
        else:
            views = []
            if list_view:
                views.append((list_view.id, 'list'))
            if form_view:
                views.append((form_view.id, 'form'))
            action.update({
                'view_mode': 'list,form',
                'views': views,
            })
        return action

    def action_view_mobilization_received(self):
        self.ensure_one()
        records = self.env['ages.mobilization.advance'].search([('project_id', '=', self.id)])
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Mobilization Received'),
            'res_model': 'ages.mobilization.advance',
            'target': 'current',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_sub_company_id': self.ages_sub_company_id.id if 'ages_sub_company_id' in self._fields else False,
                'default_company_id': self.company_id.id,
            },
        }
        form_view = self.env.ref('ages_mobilization_received.view_ages_mobilization_advance_form', raise_if_not_found=False)
        list_view = self.env.ref('ages_mobilization_received.view_ages_mobilization_advance_list', raise_if_not_found=False)
        if len(records) == 1 and form_view:
            action.update({
                'view_mode': 'form',
                'res_id': records.id,
                'views': [(form_view.id, 'form')],
            })
        else:
            views = []
            if list_view:
                views.append((list_view.id, 'list'))
            if form_view:
                views.append((form_view.id, 'form'))
            action.update({
                'view_mode': 'list,form',
                'views': views,
            })
        return action

    def action_view_retention_release(self):
        self.ensure_one()
        records = self.env['ages.retention.recovery'].search([('project_id', '=', self.id)])
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Retention Release'),
            'res_model': 'ages.retention.recovery',
            'target': 'current',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_sub_company_id': self.ages_sub_company_id.id if 'ages_sub_company_id' in self._fields else False,
                'default_company_id': self.company_id.id,
            },
        }
        form_view = self.env.ref('ages_retention_recovery.view_ages_retention_recovery_form', raise_if_not_found=False)
        list_view = self.env.ref('ages_retention_recovery.view_ages_retention_recovery_list', raise_if_not_found=False)
        if len(records) == 1 and form_view:
            action.update({
                'view_mode': 'form',
                'res_id': records.id,
                'views': [(form_view.id, 'form')],
            })
        else:
            views = []
            if list_view:
                views.append((list_view.id, 'list'))
            if form_view:
                views.append((form_view.id, 'form'))
            action.update({
                'view_mode': 'list,form',
                'views': views,
            })
        return action

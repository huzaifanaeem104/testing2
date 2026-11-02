# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ages_project_configs.models.res_company import AMOUNT_BASE_SELECTION


class AgesContract(models.Model):
    _name = 'ages.contract'
    _inherit = ['ages.contract', 'mail.thread', 'mail.activity.mixin']
    _description = 'Contract'
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Contract Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    project_wise_seq = fields.Integer(
        string='Project-Wise Sequence',
        copy=False,
        readonly=True,
        default=0,
        index=True,
    )
    project_wise_name = fields.Char(
        string='Project-Wise Contract',
        compute='_compute_project_wise_name',
        store=True,
        index=True,
    )
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('running', 'Running'),
            ('closed', 'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='new',
        required=True,
        copy=False,
        tracking=True,
        index=True,
    )
    is_locked = fields.Boolean(
        string='Locked',
        default=False,
        copy=False,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        required=True,
        tracking=True,
        domain="[('parent_id', '=', False)]",
    )
    date_start = fields.Date(string='Start Date', tracking=True)
    date_close = fields.Date(string='Close Date', tracking=True)
    contract_description = fields.Text(
        string='Contract Description',
        tracking=True,
    )
    sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    scope_project_description = fields.Char(
        string='Scope Project Description',
        help='Title printed at the top of Contract Scope (usually the project / company name).',
    )
    scope_line_ids = fields.One2many(
        comodel_name='ages.contract.scope.line',
        inverse_name='contract_id',
        string='Contract Scope Breakdown Lines',
        copy=True,
    )

    # ---- Amounts ----
    total_work_done_value = fields.Integer(
        string='Total Contract Value (Rs)',
        compute='_compute_total_work_done_value',
        store=True,
        readonly=False,
        default=0,
        tracking=True,
        help='Full contract value before rebate. If Contract Details lines exist, this is filled from them and cannot be typed.\n'
             'Formula: sum of scope Before Rebate, or typed if there are no scope lines.',
    )
    rebate_percent = fields.Float(
        string='Rebate (%)',
        digits=(16, 3),
        default=0.0,
        help='Discount on the full contract. Changing the % updates Rebate Amount and every scope line After Rebate.\n'
             'Formula: Rebate Amount = Total Contract Value × Rebate % / 100.',
    )
    rebate_amount = fields.Float(
        string='Rebate Amount (Rs)',
        compute='_compute_rebate_amount',
        inverse='_inverse_rebate_amount',
        store=True,
        readonly=False,
        digits=(16, 2),
        help='Rupees taken off the contract as rebate. You can type the amount; Rebate % is then recalculated.\n'
             'Formula: Total Contract Value × Rebate % / 100.\n'
             'If scope lines exist: Total Contract Value − sum(After Rebate).',
    )
    material_recovery = fields.Float(
        string='Material Recovery (Rs)',
        compute='_compute_material_recovery',
        store=True,
        digits=(16, 2),
        help='Value of materials to recover from the client over the whole contract. Comes from the Recovery Material tab.\n'
             'Formula: sum of Recovery Material lines (Quantity × Rate).',
    )
    work_done_ex_rebate = fields.Float(
        string='Contract-Ex. Rebate (Rs)',
        compute='_compute_work_done_ex_rebate',
        store=True,
        digits=(16, 2),
        help='Contract value after rebate is removed. Used as Amount Base option C.\n'
             'Formula: Total Contract Value − Rebate Amount.\n'
             'If scope lines exist: sum of After Rebate.',
    )
    work_done_ex_rebate_mr = fields.Float(
        string='Contract-Ex Rebate & MR (Rs)',
        compute='_compute_work_done_ex_rebate_mr',
        store=True,
        digits=(16, 2),
        help='Contract value after rebate and after material recovery. Used as Amount Base option E (usual default for Mob / Ret / Sales Tax).\n'
             'Formula: Contract-Ex. Rebate − Material Recovery.',
    )
    mobilization_percent = fields.Float(
        string='Mobilization (%)',
        digits=(16, 2),
        default=0.0,
        help='Share of the contract taken as mobilization advance (received separately, then recovered on running bills).\n'
             'Formula: Total Mobilization Amount = Mobilization Amount Base × Mobilization % / 100.',
    )
    total_mobilization_amount = fields.Float(
        string='Total Mobilization Amount (Rs)',
        compute='_compute_total_mobilization_amount',
        inverse='_inverse_total_mobilization_amount',
        store=True,
        readonly=False,
        digits=(16, 2),
        help='Mobilization advance on the full contract. You can type an override; % or Amount Base changes recompute it.\n'
             'Formula: Mobilization Amount Base × Mobilization % / 100.',
    )
    sales_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Sales Tax (%)',
        domain="[('type_tax_use', '=', 'sale'), ('tax_scope', '=', 'service'), "
               "('active', '=', True), ('id', 'in', allowed_sales_tax_ids)]",
        check_company=True,
        help='Provincial sales tax rate on the contract (e.g. 15% Sindh SRB). Not income WTH.\n'
             'Formula: selected tax % × Sales Tax Amount Base (Account Base tab).',
    )
    sales_tax_amount = fields.Float(
        string='Sales Tax Amount (Rs)',
        compute='_compute_sales_tax_amount',
        store=True,
        digits=(16, 2),
        help='Sales tax on the full contract. WTH on Sales Tax is then computed from this amount.\n'
             'Formula: Sales Tax % × Sales Tax Amount Base (A = Total Contract Value, C = Ex. Rebate, or E = Ex Rebate & MR).',
    )
    wth_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='WTH (%)',
        domain="[('is_withholding_tax_on_payment', '=', True), ('active', '=', True), "
               "('id', 'in', allowed_wth_tax_ids)]",
        check_company=True,
        help='Income withholding (WH TAX) on the contract. This is not WTH on Sales Tax (WHSRB). The amount may show as negative because the tax rate is negative.\n'
             'Formula: selected tax % applied on the WTH base (see WTH Amount).',
    )
    wth_amount = fields.Float(
        string='WTH Amount (Rs)',
        compute='_compute_wth_amount',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='Income tax withheld on the full contract (WH TAX). Shown with the tax sign (usually negative).\n'
             'WTH base = Ex Rebate & MR + Sales Tax − |WTH on Sales Tax|'
             ' − Mobilization (only if WHT on Mobilization is ticked)'
             ' − Retention (only if WHT on Retention is ticked).\n'
             'Formula: WTH % × WTH base.',
    )
    wth_on_sales_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='WTH on Sales Tax (%)',
        domain="[('type_tax_use', '=', 'sale'), ('tax_scope', '=', 'service'), "
               "('active', '=', True), ('amount', '<', 0), "
               "('id', 'in', allowed_wth_on_sales_tax_ids)]",
        check_company=True,
        help='Share of sales tax the client withholds (WHSRB, e.g. 20/80). This is not income WTH (WH TAX).\n'
             'Formula: selected tax % × Sales Tax Amount.',
    )
    wth_on_sales_tax_amount = fields.Float(
        string='WTH on Sales Tax',
        compute='_compute_wth_on_sales_tax_amount',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='Sales tax the client keeps on the contract (WHSRB). Usually negative because the tax rate is negative.\n'
             'Formula: WTH on Sales Tax % × Sales Tax Amount.',
    )
    wht_on_mobilization = fields.Boolean(
        string='WHT on Mobilization',
        default=True,
        tracking=True,
        help='Tick if mobilization should not be taxed again for income WTH. Also used when paying the Mobilization invoice.\n'
             'Formula: if ticked, WTH base = … − Total Mobilization Amount.',
    )
    wht_on_retention = fields.Boolean(
        string='WHT on Retention',
        default=True,
        tracking=True,
        help='Tick if retention should not be taxed again for income WTH. Also used when paying Retention Release.\n'
             'Formula: if ticked, WTH base = … − Total Retention Amount.',
    )
    allowed_sales_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        related='sub_company_id.sales_tax_ids',
        string='Allowed Sales Taxes',
    )
    allowed_wth_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        related='sub_company_id.wth_tax_ids',
        string='Allowed WTH Taxes',
    )
    allowed_wth_on_sales_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        related='sub_company_id.wth_on_sales_tax_ids',
        string='Allowed WTH on Sales Tax',
    )

    # ---- Amount Base (tab 4) ----
    mobilization_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Mobilization Amount-Base',
        tracking=True,
        help='Which contract figure Mobilization % is applied to. Defaults from Project Settings.\n'
             'A = Total Contract Value, C = Ex. Rebate, E = Ex Rebate & MR (usual default).\n'
             'Formula: Total Mobilization Amount = selected base × Mobilization % / 100.',
    )
    retention_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Retention Amount-Base',
        tracking=True,
        help='Which contract figure Retention % is applied to. Defaults from Project Settings.\n'
             'A = Total Contract Value, C = Ex. Rebate, E = Ex Rebate & MR (usual default).\n'
             'Formula: Total Retention Amount = selected base × Retention % / 100.',
    )
    sales_tax_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Sales Tax Amount Base',
        tracking=True,
        help='Which contract figure Sales Tax % is applied to. Used only for Sales Tax Amount — not for income WTH.\n'
             'A = Total Contract Value, C = Ex. Rebate, E = Ex Rebate & MR (usual default).\n'
             'Formula: Sales Tax Amount = selected base × Sales Tax % / 100.',
    )

    # ---- Recovery Material lines ----
    material_line_ids = fields.One2many(
        comodel_name='ages.contract.material.line',
        inverse_name='contract_id',
        string='Recovery Material',
    )

    # ---- Linked records (4-way link) ----
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        copy=False,
        readonly=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        copy=False,
        readonly=True,
    )
    location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Location',
        copy=False,
        readonly=True,
    )

    # ---- Downstream docs (stub links for later sheets) ----
    running_bill_ids = fields.One2many(
        comodel_name='ages.running.bill',
        inverse_name='contract_id',
        string='Running Bills',
        copy=False,
    )
    mobilization_advance_id = fields.Many2one(
        comodel_name='ages.mobilization.advance',
        string='Mobilization Receiving',
        copy=False,
        readonly=True,
    )
    retention_recovery_id = fields.Many2one(
        comodel_name='ages.retention.recovery',
        string='Retention Release',
        copy=False,
        readonly=True,
    )

    # ---- Documents & smart buttons ----
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='ages_contract_ir_attachment_rel',
        column1='contract_id',
        column2='attachment_id',
        string='Documents Attached',
    )
    running_bill_count = fields.Integer(
        string='Running Bills Count',
        compute='_compute_smart_button_counts',
    )
    mobilization_count = fields.Integer(
        string='Mobilization Count',
        compute='_compute_smart_button_counts',
    )
    retention_count = fields.Integer(
        string='Retention Release Count',
        compute='_compute_smart_button_counts',
    )
    project_count = fields.Integer(
        string='Project Count',
        compute='_compute_smart_button_counts',
    )

    @api.depends('project_wise_seq', 'project_id', 'project_id.name')
    def _compute_project_wise_name(self):
        for contract in self:
            if contract.project_wise_seq and contract.project_id:
                contract.project_wise_name = _('Contract %s - %s') % (
                    contract.project_wise_seq,
                    contract.project_id.display_name,
                )
            else:
                contract.project_wise_name = False

    def _ages_next_project_wise_seq(self, project_id, exclude_ids=None):
        """Next Contract N for this project. System sequence on name is unchanged."""
        if not project_id:
            return 0
        query = """
            SELECT COALESCE(MAX(project_wise_seq), 0)
              FROM ages_contract
             WHERE project_id = %s
        """
        params = [project_id]
        exclude_ids = [cid for cid in (exclude_ids or []) if cid]
        if exclude_ids:
            query += " AND id NOT IN %s"
            params.append(tuple(exclude_ids))
        self.env.cr.execute(query, params)
        return (self.env.cr.fetchone()[0] or 0) + 1

    def _ages_backfill_project_wise_numbers(self):
        """Assign project-wise numbers to existing contracts that do not have one."""
        self.env.cr.execute("""
            SELECT id FROM ages_contract
             WHERE project_id IS NOT NULL
               AND COALESCE(project_wise_seq, 0) = 0
             ORDER BY project_id, id
        """)
        ids = [row[0] for row in self.env.cr.fetchall()]
        if not ids:
            return
        last_by_project = {}
        self.env.cr.execute("""
            SELECT project_id, COALESCE(MAX(project_wise_seq), 0)
              FROM ages_contract
             WHERE project_id IS NOT NULL
             GROUP BY project_id
        """)
        last_by_project.update(self.env.cr.fetchall())
        for contract in self.browse(ids):
            project_id = contract.project_id.id
            last_by_project[project_id] = last_by_project.get(project_id, 0) + 1
            super(AgesContract, contract).write({
                'project_wise_seq': last_by_project[project_id],
            })

    def _auto_init(self):
        super()._auto_init()
        if 'project_wise_seq' in self._fields:
            self._ages_backfill_project_wise_numbers()

    @api.depends('running_bill_ids', 'mobilization_advance_id', 'retention_recovery_id', 'project_id')
    def _compute_smart_button_counts(self):
        for contract in self:
            contract.running_bill_count = len(contract.running_bill_ids)
            contract.mobilization_count = 1 if contract.mobilization_advance_id else 0
            contract.retention_count = 1 if contract.retention_recovery_id else 0
            contract.project_count = 1 if contract.project_id else 0

    def action_view_running_bills(self):
        self.ensure_one()
        return self._action_view_linked_records(
            model='ages.running.bill',
            records=self.running_bill_ids,
            name=_('Running Bills'),
            context={'default_contract_id': self.id},
        )

    def action_view_mobilization_received(self):
        self.ensure_one()
        return self._action_view_linked_records(
            model='ages.mobilization.advance',
            records=self.mobilization_advance_id,
            name=_('Mobilization Received'),
            context={'default_contract_id': self.id},
        )

    def action_view_retention_release(self):
        self.ensure_one()
        return self._action_view_linked_records(
            model='ages.retention.recovery',
            records=self.retention_recovery_id,
            name=_('Retention Release'),
            context={'default_contract_id': self.id},
        )

    def action_view_project(self):
        self.ensure_one()
        return self._action_view_linked_records(
            model='project.project',
            records=self.project_id,
            name=_('Project'),
            context={'default_ages_contract_id': self.id},
        )

    def _action_view_linked_records(self, model, records, name, context=None):
        """Open form when one record, list when more than one."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'target': 'current',
            'context': context or {},
            'domain': [('id', 'in', records.ids)],
        }
        if len(records) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': records.id,
            })
        else:
            action['view_mode'] = 'list,form'
        return action

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        if 'mobilization_amount_base' in fields_list and not res.get('mobilization_amount_base'):
            res['mobilization_amount_base'] = company.ages_mobilization_amount_base or 'work_done_ex_rebate_mr'
        if 'retention_amount_base' in fields_list and not res.get('retention_amount_base'):
            res['retention_amount_base'] = company.ages_retention_amount_base or 'work_done_ex_rebate_mr'
        if 'sales_tax_amount_base' in fields_list and not res.get('sales_tax_amount_base'):
            res['sales_tax_amount_base'] = company.ages_sales_tax_amount_base or 'work_done_ex_rebate_mr'
        return res

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Location, Active Company and Analytic are fetched from the project."""
        if not self.project_id:
            return
        project = self.project_id
        if project.partner_id:
            self.partner_id = project.partner_id
        sub_company = (
            project.ages_sub_company_id
            if 'ages_sub_company_id' in project._fields else False
        )
        if sub_company:
            self.sub_company_id = sub_company
        if project.company_id:
            self.company_id = project.company_id
        self.analytic_account_id = project.account_id
        self.location_id = project.ages_location_id
        if project.date_start and not self.date_start:
            self.date_start = project.date_start
        if project.date and not self.date_close:
            self.date_close = project.date

    @api.onchange('company_id')
    def _onchange_company_id_amount_bases(self):
        if self.company_id:
            if not self.mobilization_amount_base:
                self.mobilization_amount_base = (
                    self.company_id.ages_mobilization_amount_base or 'work_done_ex_rebate_mr'
                )
            if not self.retention_amount_base:
                self.retention_amount_base = (
                    self.company_id.ages_retention_amount_base or 'work_done_ex_rebate_mr'
                )
            if not self.sales_tax_amount_base:
                self.sales_tax_amount_base = (
                    self.company_id.ages_sales_tax_amount_base or 'work_done_ex_rebate_mr'
                )

    # -------------------------------------------------------------------------
    # Amount helpers
    # -------------------------------------------------------------------------
    def _get_amount_for_base(self, base_key):
        """Return the numeric base used by Mobilization / Retention % calculations.

        Priority source for which base key applies is the contract field
        (Account Base tab). That field is defaulted from Project Settings
        but remains changeable per contract.
        """
        self.ensure_one()
        mapping = {
            'total_work_done_value': self.total_work_done_value or 0.0,
            'work_done_ex_rebate': self.work_done_ex_rebate or 0.0,
            'work_done_ex_rebate_mr': self.work_done_ex_rebate_mr or 0.0,
        }
        return mapping.get(base_key or '', 0.0)

    def _ages_get_wht_base(self):
        """WHT base: E + Sales Tax - |WTH on Sales Tax|, minus Mob/Ret when ticked.

        Sales Tax Amount Base still applies only to the Sales Tax amount itself.
        Signs of Sales Tax / WTH on Sales Tax are ignored; amounts are used.
        """
        self.ensure_one()
        base = (self.work_done_ex_rebate_mr or 0.0)
        base += abs(self.sales_tax_amount or 0.0)
        base -= abs(self.wth_on_sales_tax_amount or 0.0)
        if self.wht_on_mobilization:
            base -= abs(self.total_mobilization_amount or 0.0)
        if self.wht_on_retention:
            base -= abs(getattr(self, 'total_retention_amount', 0.0) or 0.0)
        return base

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------
    @api.depends('scope_line_ids.amount_before_rebate')
    def _compute_total_work_done_value(self):
        for contract in self:
            if contract.scope_line_ids:
                contract.total_work_done_value = int(round(sum(contract.scope_line_ids.mapped('amount_before_rebate'))))

    @api.depends('rebate_percent', 'total_work_done_value', 'scope_line_ids.amount_after_rebate')
    def _compute_rebate_amount(self):
        for contract in self:
            if contract.scope_line_ids:
                contract.rebate_amount = (contract.total_work_done_value or 0) - sum(contract.scope_line_ids.mapped('amount_after_rebate'))
            else:
                contract.rebate_amount = (contract.rebate_percent or 0.0) / 100.0 * (contract.total_work_done_value or 0)

    def _inverse_rebate_amount(self):
        for contract in self:
            if contract.total_work_done_value:
                contract.rebate_percent = round((contract.rebate_amount or 0.0) / contract.total_work_done_value * 100.0, 3)
            else:
                contract.rebate_percent = 0.0

    @api.onchange('rebate_amount')
    def _onchange_rebate_amount(self):
        if self.total_work_done_value:
            self.rebate_percent = round((self.rebate_amount or 0.0) / self.total_work_done_value * 100.0, 3)
        else:
            self.rebate_percent = 0.0
        for line in self.scope_line_ids:
            line.rebate_percent = self.rebate_percent
            rebate = (line.amount_before_rebate or 0.0) * (self.rebate_percent or 0.0) / 100.0
            line.amount_after_rebate = (line.amount_before_rebate or 0.0) - rebate

    @api.onchange('rebate_percent', 'total_work_done_value')
    def _onchange_rebate_percent_scope_lines(self):
        if not self.scope_line_ids:
            self.rebate_amount = (self.total_work_done_value or 0) * (self.rebate_percent or 0.0) / 100.0
        for line in self.scope_line_ids:
            line.rebate_percent = self.rebate_percent
            rebate = (line.amount_before_rebate or 0.0) * (self.rebate_percent or 0.0) / 100.0
            line.amount_after_rebate = (line.amount_before_rebate or 0.0) - rebate

    @api.depends('material_line_ids.amount')
    def _compute_material_recovery(self):
        for contract in self:
            contract.material_recovery = sum(contract.material_line_ids.mapped('amount'))

    @api.depends('total_work_done_value', 'rebate_amount', 'scope_line_ids.amount_after_rebate')
    def _compute_work_done_ex_rebate(self):
        for contract in self:
            if contract.scope_line_ids:
                contract.work_done_ex_rebate = sum(contract.scope_line_ids.mapped('amount_after_rebate'))
            else:
                contract.work_done_ex_rebate = (contract.total_work_done_value or 0) - (contract.rebate_amount or 0.0)

    @api.depends('work_done_ex_rebate', 'material_recovery')
    def _compute_work_done_ex_rebate_mr(self):
        for contract in self:
            contract.work_done_ex_rebate_mr = (contract.work_done_ex_rebate or 0.0) - (contract.material_recovery or 0.0)

    @api.depends(
        'mobilization_percent',
        'mobilization_amount_base',
        'total_work_done_value',
        'work_done_ex_rebate',
        'work_done_ex_rebate_mr',
    )
    def _compute_total_mobilization_amount(self):
        for contract in self:
            base_amount = contract._get_amount_for_base(contract.mobilization_amount_base)
            contract.total_mobilization_amount = (contract.mobilization_percent or 0.0) / 100.0 * base_amount

    def _inverse_total_mobilization_amount(self):
        """Allow manual override; recomputed when % or Amount-Base sources change."""
        return

    @api.depends(
        'sales_tax_id',
        'sales_tax_id.amount',
        'sales_tax_id.amount_type',
        'sales_tax_amount_base',
        'total_work_done_value',
        'work_done_ex_rebate',
        'work_done_ex_rebate_mr',
    )
    def _compute_sales_tax_amount(self):
        for contract in self:
            tax = contract.sales_tax_id
            base = contract._get_amount_for_base(
                contract.sales_tax_amount_base or 'work_done_ex_rebate_mr'
            )
            if not tax:
                contract.sales_tax_amount = 0.0
            elif tax.amount_type == 'percent':
                contract.sales_tax_amount = base * (tax.amount or 0.0) / 100.0
            elif tax.amount_type == 'fixed':
                contract.sales_tax_amount = tax.amount or 0.0
            else:
                contract.sales_tax_amount = base * (tax.amount or 0.0) / 100.0

    @api.depends(
        'wth_tax_id',
        'wth_tax_id.amount',
        'wth_tax_id.amount_type',
        'work_done_ex_rebate_mr',
        'sales_tax_amount',
        'wth_on_sales_tax_amount',
        'total_mobilization_amount',
        'wht_on_mobilization',
        'wht_on_retention',
    )
    def _compute_wth_amount(self):
        for contract in self:
            tax = contract.wth_tax_id
            base = contract._ages_get_wht_base()
            if not tax:
                contract.wth_amount = 0.0
            elif tax.amount_type == 'percent':
                contract.wth_amount = base * (tax.amount or 0.0) / 100.0
            elif tax.amount_type == 'fixed':
                contract.wth_amount = tax.amount or 0.0
            else:
                contract.wth_amount = base * (tax.amount or 0.0) / 100.0

    @api.depends(
        'wth_on_sales_tax_id',
        'wth_on_sales_tax_id.amount',
        'wth_on_sales_tax_id.amount_type',
        'sales_tax_amount',
    )
    def _compute_wth_on_sales_tax_amount(self):
        for contract in self:
            tax = contract.wth_on_sales_tax_id
            base = contract.sales_tax_amount or 0.0
            if not tax:
                contract.wth_on_sales_tax_amount = 0.0
            elif tax.amount_type == 'percent':
                contract.wth_on_sales_tax_amount = base * (tax.amount or 0.0) / 100.0
            elif tax.amount_type == 'fixed':
                contract.wth_on_sales_tax_amount = tax.amount or 0.0
            else:
                contract.wth_on_sales_tax_amount = base * (tax.amount or 0.0) / 100.0

    def _auto_init(self):
        cr = self._cr
        cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'ages_contract'
               AND column_name = 'wht_on_mobilization'
            """
        )
        column_exists = bool(cr.fetchone())
        super()._auto_init()
        if not column_exists:
            cr.execute(
                """
                UPDATE ages_contract
                   SET wht_on_mobilization = TRUE,
                       wht_on_retention = TRUE
                """
            )

    # -------------------------------------------------------------------------
    # CRUD / constraints
    # -------------------------------------------------------------------------
    @api.constrains('date_start', 'date_close')
    def _check_dates(self):
        for contract in self:
            if contract.date_start and contract.date_close and contract.date_close < contract.date_start:
                raise ValidationError(_('Close Date cannot be earlier than Start Date.'))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) in (_('New'), 'New', False):
                vals['name'] = sequence.next_by_code('ages.contract') or _('New')
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id
            )
            vals.setdefault(
                'mobilization_amount_base',
                company.ages_mobilization_amount_base or 'work_done_ex_rebate_mr',
            )
            vals.setdefault(
                'retention_amount_base',
                company.ages_retention_amount_base or 'work_done_ex_rebate_mr',
            )
            vals.setdefault(
                'sales_tax_amount_base',
                company.ages_sales_tax_amount_base or 'work_done_ex_rebate_mr',
            )
            if vals.get('project_id'):
                project = self.env['project.project'].browse(vals['project_id'])
                if not vals.get('analytic_account_id') and project.account_id:
                    vals['analytic_account_id'] = project.account_id.id
                if not vals.get('location_id') and project.ages_location_id:
                    vals['location_id'] = project.ages_location_id.id
                if not vals.get('sub_company_id') and 'ages_sub_company_id' in project._fields and project.ages_sub_company_id:
                    vals['sub_company_id'] = project.ages_sub_company_id.id
                if not vals.get('partner_id') and project.partner_id:
                    vals['partner_id'] = project.partner_id.id
                if not vals.get('company_id') and project.company_id:
                    vals['company_id'] = project.company_id.id
            if vals.get('project_id') and not vals.get('project_wise_seq'):
                vals['project_wise_seq'] = self._ages_next_project_wise_seq(vals['project_id'])
        return super().create(vals_list)

    def write(self, vals):
        old_project_ids = {}
        if 'project_id' in vals:
            old_project_ids = {contract.id: contract.project_id.id for contract in self}
        if not self.env.context.get('ages_skip_lock'):
            locked = self.filtered('is_locked')
            if locked:
                extra = {
                    name for name in vals
                    if name not in self._AGES_LOCK_ALLOWED_FIELDS
                    and name in self._fields
                    and not self._fields[name].compute
                    and not self._fields[name].related
                }
                if extra:
                    raise UserError(_(
                        'This contract is locked. Unlock it before changing any fields.'
                    ))
        res = super().write(vals)
        if 'project_id' in vals:
            for contract in self:
                old_project_id = old_project_ids.get(contract.id)
                extra_vals = {}
                if contract.project_id and (
                    not contract.project_wise_seq
                    or old_project_id != contract.project_id.id
                ):
                    extra_vals['project_wise_seq'] = self._ages_next_project_wise_seq(
                        contract.project_id.id,
                        exclude_ids=contract.ids,
                    )
                if contract.project_id and old_project_id != contract.project_id.id:
                    project = contract.project_id
                    if 'analytic_account_id' not in vals:
                        extra_vals['analytic_account_id'] = project.account_id.id
                    if 'location_id' not in vals:
                        extra_vals['location_id'] = project.ages_location_id.id
                    if 'sub_company_id' not in vals and 'ages_sub_company_id' in project._fields:
                        extra_vals['sub_company_id'] = project.ages_sub_company_id.id
                if extra_vals:
                    super(AgesContract, contract).write(extra_vals)
        return res

    _AGES_LOCK_ALLOWED_FIELDS = frozenset({
        'is_locked',
        'state',
        'project_wise_seq',
        'message_ids',
        'message_follower_ids',
        'message_main_attachment_id',
        'activity_ids',
        'website_message_ids',
        'mobilization_advance_id',
        'retention_recovery_id',
        'running_bill_ids',
        'attachment_ids',
    })

    # -------------------------------------------------------------------------
    # Status buttons
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for contract in self:
            if contract.state != 'new':
                raise UserError(_('Only New contracts can be confirmed.'))
            contract = contract.with_context(ages_skip_lock=True)
            contract._create_linked_project_analytic_location()
            contract.write({
                'state': 'running',
                'is_locked': True,
            })
        return True

    def action_lock(self):
        for contract in self:
            if contract.is_locked:
                raise UserError(_('This contract is already locked.'))
            if contract.state == 'cancelled':
                raise UserError(_('Cancelled contracts cannot be locked.'))
            contract.is_locked = True
        return True

    def action_unlock(self):
        for contract in self:
            if not contract.is_locked:
                raise UserError(_('This contract is not locked.'))
            contract.is_locked = False
        return True

    def action_reopen(self):
        for contract in self:
            if contract.state != 'closed':
                raise UserError(_('Only Closed contracts can be reopened.'))
            contract.with_context(ages_skip_lock=True).write({
                'state': 'running',
                'is_locked': True,
            })
        return True

    def action_cancel(self):
        for contract in self:
            if contract.state != 'new':
                raise UserError(_('Only New contracts can be cancelled.'))
            contract.state = 'cancelled'
        return True

    def action_reset(self):
        for contract in self:
            if contract.state != 'cancelled':
                raise UserError(_('Only Cancelled contracts can be reset to New.'))
            contract.state = 'new'
        return True

    def action_close(self):
        for contract in self:
            if contract.state != 'running':
                raise UserError(_('Only Running contracts can be closed.'))
            contract.state = 'closed'
        return True

    # -------------------------------------------------------------------------
    # Downstream document buttons (stubs + link guards for next sheets)
    # -------------------------------------------------------------------------
    def action_create_ra_bill(self):
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('Running Bills can only be created for Running contracts.'))
        bill = self.env['ages.running.bill'].create({
            'name': _('RA/%s/%s') % (self.name, len(self.running_bill_ids) + 1),
            'contract_id': self.id,
            'company_id': self.company_id.id,
        })
        return self._action_open_record(bill)

    def action_mobilization_receiving(self):
        """Open Mobilization Received form; link is set only when the record is saved."""
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('Mobilization Receiving is only available on Running contracts.'))
        if not (self.total_mobilization_amount or 0.0):
            raise UserError(_(
                'Mobilization Receiving is not available because Total Mobilization Amount is zero.'
            ))
        if self.mobilization_advance_id:
            return self._action_open_record(self.mobilization_advance_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mobilization Received'),
            'res_model': 'ages.mobilization.advance',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_contract_id': self.id,
                'default_project_id': self.project_id.id,
                'default_company_id': self.company_id.id,
                'default_mobilization_amount': self.total_mobilization_amount or 0.0,
                'default_date': fields.Date.context_today(self),
            },
        }

    def action_retention_release(self):
        """Open Retention Release form; link is set only when the record is saved."""
        self.ensure_one()
        if self.state != 'closed':
            raise UserError(_('Retention Release is only available on Closed contracts.'))
        if self.retention_recovery_id:
            return self._action_open_record(self.retention_recovery_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retention Release'),
            'res_model': 'ages.retention.recovery',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_contract_id': self.id,
                'default_project_id': self.project_id.id,
                'default_company_id': self.company_id.id,
                'default_retention_amount': getattr(self, 'total_retention_amount', 0.0) or 0.0,
                'default_date': fields.Date.context_today(self),
            },
        }

    def _action_open_record(self, record):
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # Auto-create Project + Analytic + Location on Confirm
    # -------------------------------------------------------------------------
    def _create_linked_project_analytic_location(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Client is required before confirming the contract.'))
        if not self.sub_company_id:
            raise UserError(_('Active Company is required before confirming the contract.'))

        company = self.company_id
        short_code = self.sub_company_id.short_code or ''
        linked_name = '%s %s' % (self.partner_id.name, short_code)
        linked_name = linked_name.strip()

        analytic = self.analytic_account_id
        if not analytic:
            plan = company.ages_default_analytic_plan_id
            if not plan:
                raise UserError(_(
                    'Please set Default Analytic Plans in Project → Configuration → Settings '
                    'before confirming a contract.'
                ))
            analytic = self.env['account.analytic.account'].create({
                'name': linked_name,
                'plan_id': plan.id,
                'partner_id': self.partner_id.id,
                'company_id': company.id,
                'ages_contract_id': self.id,
            })
            self.analytic_account_id = analytic.id

        project = self.project_id
        if not project:
            project = self.env['project.project'].create({
                'name': linked_name,
                'partner_id': self.partner_id.id,
                'date_start': self.date_start,
                'date': self.date_close,
                'company_id': company.id,
                'account_id': analytic.id,
                'ages_contract_id': self.id,
            })
            self.project_id = project.id

        location = self.location_id
        if not location:
            parent = company.ages_default_parent_location_id
            if not parent:
                raise UserError(_(
                    'Please set Default Parent Location in Project → Configuration → Settings '
                    'before confirming a contract.'
                ))
            location = self.env['stock.location'].create({
                'name': self.partner_id.name,
                'usage': 'internal',
                'location_id': parent.id,
                'company_id': company.id,
                'ages_contract_id': self.id,
                'ages_project_id': project.id,
                'ages_analytic_account_id': analytic.id,
            })
            self.location_id = location.id

        # Keep the 4-way link in sync on every related record
        analytic.write({
            'ages_contract_id': self.id,
            'ages_project_id': project.id,
            'ages_location_id': location.id,
        })
        project.write({
            'ages_contract_id': self.id,
            'ages_location_id': location.id,
            'account_id': analytic.id,
        })
        location.write({
            'ages_contract_id': self.id,
            'ages_project_id': project.id,
            'ages_analytic_account_id': analytic.id,
        })

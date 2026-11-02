# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AgesExpenseLine(models.Model):
    _name = 'ages.expense.line'
    _description = 'Expense Line Item'
    _order = 'sequence, id'

    expense_id = fields.Many2one(
        'ages.expense',
        string='Expense Reference',
        ondelete='cascade',
        required=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=False,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        compute='_compute_analytic_account_id',
        store=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        # Same idea as journal items: every non-deprecated account of this
        # company (any type). Company comes from the expense / top switcher
        # via company_id + check_company — not from other companies.
        domain="[('deprecated', '=', False)]",
        required=True,
        check_company=True,
        help='All accounts of the company selected in the top bar (any type). '
             'The journal entry debits this account and credits the payment journal.',
    )
    company_id = fields.Many2one(
        related='expense_id.company_id',
        store=True,
        readonly=True,
        index=True,
    )
    is_payable_account = fields.Boolean(
        string='Payable Account',
        compute='_compute_is_payable_account',
        store=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=False,
        domain="['|', ('supplier_rank', '>', 0), ('is_company', '=', True)]",
        help='Required when Expense Account is a Payable account.',
    )
    name = fields.Char(
        string='Description',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        default=0.0,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='expense_id.currency_id',
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'ages_expense_line_attachment_rel',
        'line_id',
        'attachment_id',
        string='Attach Receipt',
    )

    @api.depends('account_id', 'account_id.account_type')
    def _compute_is_payable_account(self):
        for line in self:
            line.is_payable_account = line.account_id.account_type == 'liability_payable'

    @api.depends('project_id', 'project_id.account_id')
    def _compute_analytic_account_id(self):
        for line in self:
            analytic = False
            project = line.project_id
            if project:
                if 'account_id' in project._fields and project.account_id:
                    analytic = project.account_id
                elif 'analytic_account_id' in project._fields and project.analytic_account_id:
                    analytic = project.analytic_account_id
            line.analytic_account_id = analytic

    def _ages_get_sub_company(self):
        self.ensure_one()
        project = self.project_id
        if project and 'ages_sub_company_id' in project._fields and project.ages_sub_company_id:
            return project.ages_sub_company_id
        return False

    def _ages_analytic_distribution(self):
        """100% distribution on this line's project analytic account."""
        self.ensure_one()
        if not self.analytic_account_id:
            return False
        return {str(self.analytic_account_id.id): 100.0}

    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("The expense line amount must be greater than zero."))

    @api.constrains('project_id')
    def _check_project_analytic(self):
        for line in self:
            if line.project_id and not line.analytic_account_id:
                raise ValidationError(_(
                    "Project '%s' has no analytic account. "
                    "Set an analytic account on the project before using it on expenses."
                ) % line.project_id.display_name)

    @api.constrains('account_id', 'partner_id')
    def _check_payable_requires_partner(self):
        for line in self:
            if line.account_id.account_type == 'liability_payable' and not line.partner_id:
                raise ValidationError(_(
                    "Partner is required when Expense Account '%s' is a Payable account."
                ) % (line.account_id.display_name or line.account_id.code))

# -*- coding: utf-8 -*-

from odoo import fields, models


AMOUNT_BASE_SELECTION = [
    ('work_done_ex_rebate_mr', 'Contract-Ex Rebate & MR (Rs)'),
    ('work_done_ex_rebate', 'Contract-Ex. Rebate (Rs)'),
    ('total_work_done_value', 'Total Contract Value (Rs)'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    ages_work_done_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Work Done Account',
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', id)]",
    )
    ages_mobilization_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Mobilization Account',
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', id)]",
    )
    ages_retention_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Retention Account',
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', id)]",
        help='Client retention held on running bills (e.g. 101001 RETENTION MONEY).',
    )
    ages_vendor_retention_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Vendor Retention Payable',
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', id), ('account_type', 'in', ('liability_payable', 'liability_current', 'liability_non_current'))]",
        help='Amount AGES holds from subcontractors (e.g. 201003 RETENTION MONEY PAYABLES). Do not use the client Retention Account.',
    )
    ages_default_parent_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Default Parent Location',
        check_company=True,
        domain="[('usage', '=', 'view'), ('company_id', 'in', [id, False])]",
    )
    ages_default_analytic_plan_id = fields.Many2one(
        comodel_name='account.analytic.plan',
        string='Analytic Plans',
    )
    ages_mobilization_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Mobilization Amount-Base',
    )
    ages_retention_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Retention Amount-Base',
    )
    ages_sales_tax_amount_base = fields.Selection(
        selection=AMOUNT_BASE_SELECTION,
        string='Sales Tax Amount Base',
        default='work_done_ex_rebate_mr',
    )

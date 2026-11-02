# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_work_done_account_id = fields.Many2one(
        comodel_name='account.account',
        related='company_id.ages_work_done_account_id',
        string='Work Done Account',
        readonly=False,
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
    )
    ages_mobilization_account_id = fields.Many2one(
        comodel_name='account.account',
        related='company_id.ages_mobilization_account_id',
        string='Mobilization Account',
        readonly=False,
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
    )
    ages_retention_account_id = fields.Many2one(
        comodel_name='account.account',
        related='company_id.ages_retention_account_id',
        string='Retention Account',
        readonly=False,
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
    )
    ages_vendor_retention_account_id = fields.Many2one(
        comodel_name='account.account',
        related='company_id.ages_vendor_retention_account_id',
        string='Vendor Retention Payable',
        readonly=False,
        check_company=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id), ('account_type', 'in', ('liability_payable', 'liability_current', 'liability_non_current'))]",
    )
    ages_default_parent_location_id = fields.Many2one(
        comodel_name='stock.location',
        related='company_id.ages_default_parent_location_id',
        string='Location',
        readonly=False,
        check_company=True,
        domain="[('usage', '=', 'view'), ('company_id', 'in', [company_id, False])]",
    )
    ages_default_analytic_plan_id = fields.Many2one(
        comodel_name='account.analytic.plan',
        related='company_id.ages_default_analytic_plan_id',
        string='Analytic Plans',
        readonly=False,
    )
    ages_mobilization_amount_base = fields.Selection(
        related='company_id.ages_mobilization_amount_base',
        string='Mobilization Amount-Base',
        readonly=False,
    )
    ages_retention_amount_base = fields.Selection(
        related='company_id.ages_retention_amount_base',
        string='Retention Amount-Base',
        readonly=False,
    )
    ages_sales_tax_amount_base = fields.Selection(
        related='company_id.ages_sales_tax_amount_base',
        string='Sales Tax Amount Base',
        readonly=False,
    )

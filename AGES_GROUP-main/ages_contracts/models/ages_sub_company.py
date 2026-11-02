# -*- coding: utf-8 -*-

from odoo import fields, models


class AgesSubCompany(models.Model):
    _inherit = 'ages.sub.company'

    sales_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='ages_sub_company_sales_tax_rel',
        column1='sub_company_id',
        column2='tax_id',
        string='Sales Tax (%)',
        domain="[('type_tax_use', '=', 'sale'), ('tax_scope', '=', 'service'), "
               "('active', '=', True)]",
        check_company=True,
        help='Taxes offered on Contract and Running Bill when this Active Company is selected.',
    )
    wth_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='ages_sub_company_wth_tax_rel',
        column1='sub_company_id',
        column2='tax_id',
        string='WTH (%)',
        domain="[('is_withholding_tax_on_payment', '=', True), ('active', '=', True)]",
        check_company=True,
        help='Withholding taxes offered on Contract and Running Bill for this Active Company.',
    )
    wth_on_sales_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='ages_sub_company_wth_on_sales_tax_rel',
        column1='sub_company_id',
        column2='tax_id',
        string='WTH on Sales Tax (%)',
        domain="[('type_tax_use', '=', 'sale'), ('tax_scope', '=', 'service'), "
               "('active', '=', True), ('amount', '<', 0)]",
        check_company=True,
        help='WTH on Sales Tax options offered on Contract and Running Bill for this Active Company.',
    )

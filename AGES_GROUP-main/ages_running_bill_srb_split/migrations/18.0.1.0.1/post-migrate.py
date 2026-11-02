# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    if hasattr(env['account.move'], '_ages_cancel_withheld_sales_tax_refunds'):
        env['account.move']._ages_cancel_withheld_sales_tax_refunds()

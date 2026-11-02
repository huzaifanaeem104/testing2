# -*- coding: utf-8 -*-


def post_init_apply_srb_split(env):
    # Temporary AGES-SRB-WHT refunds are obsolete (invoices already net of WTH).
    env['account.move']._ages_cancel_withheld_sales_tax_refunds()


def uninstall_revert_srb_split(env):
    env['account.move']._ages_cancel_withheld_sales_tax_refunds()

# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.ages_account_dimensions.hooks import cancel_ages_srb_wht_refunds

    env = api.Environment(cr, SUPERUSER_ID, {})
    cancel_ages_srb_wht_refunds(env)

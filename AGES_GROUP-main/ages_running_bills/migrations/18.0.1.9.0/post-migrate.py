# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    from odoo.addons.ages_running_bills.hooks import revert_srb_withheld_credit_notes

    env = api.Environment(cr, SUPERUSER_ID, {})
    revert_srb_withheld_credit_notes(env)

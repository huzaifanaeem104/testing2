# -*- coding: utf-8 -*-

from odoo import models


class AgesRunningBill(models.Model):
    _inherit = 'ages.running.bill'

    # Invoice booking lives on ages_running_bills:
    # SRB credit 100% + SRB debit WTH share (20%) + Mob/Ret lines.

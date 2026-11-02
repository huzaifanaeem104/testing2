# -*- coding: utf-8 -*-

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super()._action_done()
        slips = self.env["ages.civil.material.slip"].search(
            [("picking_id", "in", self.ids), ("state", "=", "confirmed")]
        )
        if slips:
            slips.write({"state": "received"})
        return res

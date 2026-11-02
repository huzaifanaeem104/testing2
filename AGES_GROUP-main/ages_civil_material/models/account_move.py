# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    ages_civil_slip_ids = fields.One2many(
        "ages.civil.material.slip",
        "bill_id",
        string="Civil Material Slips",
        readonly=True,
    )
    ages_is_civil_material_bill = fields.Boolean(
        string="Civil Material Bill",
        copy=False,
    )


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    ages_civil_slip_id = fields.Many2one(
        "ages.civil.material.slip",
        string="Civil Material Slip",
        copy=False,
        index=True,
    )
    ages_civil_truck_no = fields.Char(string="Truck #", copy=False)
    ages_civil_measurement_slip = fields.Char(string="Measurement Slip #", copy=False)
    ages_civil_slip_date = fields.Date(string="Slip Date", copy=False)

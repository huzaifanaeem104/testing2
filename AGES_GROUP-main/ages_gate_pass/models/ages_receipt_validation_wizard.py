# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class AgesReceiptValidationWizard(models.TransientModel):
    _name = 'ages.receipt.validation.wizard'
    _description = 'Confirm Receipt Destination Location'

    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Receipt',
        required=True,
        readonly=True,
    )
    location_dest_id = fields.Many2one(
        comodel_name='stock.location',
        string='Destination Location',
        required=True,
        domain="[('usage', '=', 'internal')]",
    )

    def action_validate(self):
        self.ensure_one()
        if self.location_dest_id and self.picking_id.location_dest_id != self.location_dest_id:
            self.picking_id.write({'location_dest_id': self.location_dest_id.id})
        return self.picking_id.with_context(skip_location_check_wizard=True).button_validate()

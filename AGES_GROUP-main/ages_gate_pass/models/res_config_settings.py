# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_gate_pass_in_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Gate In Sequence',
        compute='_compute_ages_gate_pass_sequences',
    )
    ages_gate_pass_out_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Gate Out Sequence',
        compute='_compute_ages_gate_pass_sequences',
    )
    ages_gate_pass_rgp_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='RGP Sequence',
        compute='_compute_ages_gate_pass_sequences',
    )

    def _compute_ages_gate_pass_sequences(self):
        Sequence = self.env['ir.sequence']
        for wizard in self:
            wizard.ages_gate_pass_in_sequence_id = Sequence.search(
                [('code', '=', 'gate.pass.in.sequence')], limit=1,
            )
            wizard.ages_gate_pass_out_sequence_id = Sequence.search(
                [('code', '=', 'gate.pass.out.sequence')], limit=1,
            )
            wizard.ages_gate_pass_rgp_sequence_id = Sequence.search(
                [('code', '=', 'gate.pass.rgp.sequence')], limit=1,
            )

    def action_open_gate_pass_sequences(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Gate Pass Sequences',
            'res_model': 'ir.sequence',
            'view_mode': 'list,form',
            'domain': [
                ('code', 'in', [
                    'gate.pass.in.sequence',
                    'gate.pass.out.sequence',
                    'gate.pass.rgp.sequence',
                ]),
            ],
            'target': 'current',
        }

    def action_open_gate_pass_groups(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Gate Pass Groups',
            'res_model': 'res.groups',
            'view_mode': 'list,form',
            'domain': [
                ('category_id', '=', self.env.ref('ages_gate_pass.module_category_ages_gate_pass').id),
            ],
            'target': 'current',
        }

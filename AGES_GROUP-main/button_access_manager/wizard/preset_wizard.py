# -*- coding: utf-8 -*-
from odoo import fields, models

from odoo.addons.button_access_manager.models.access_profile import PRESET_SELECTION


class AccessProfilePresetWizard(models.TransientModel):
    _name = 'access.profile.preset.wizard'
    _description = 'Apply Access Profile Preset'

    profile_id = fields.Many2one('access.profile', required=True, ondelete='cascade')
    preset = fields.Selection(PRESET_SELECTION, required=True, default='view_only_all')

    def action_apply(self):
        self.ensure_one()
        self.profile_id.apply_preset(self.preset)
        return {'type': 'ir.actions.act_window_close'}

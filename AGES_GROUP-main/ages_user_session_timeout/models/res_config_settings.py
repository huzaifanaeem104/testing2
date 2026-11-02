# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .res_users import PARAM_GROUP_IDS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ages_session_timeout_enabled = fields.Boolean(
        string='Default inactivity timeout',
        config_parameter='ages_user_session_timeout.enabled',
        default=True,
        help='Used when a user\'s policy is "Use default settings". Custom users still time out if this is off.',
    )
    ages_session_timeout_idle_minutes = fields.Integer(
        string='Default idle timeout (minutes)',
        config_parameter='ages_user_session_timeout.idle_minutes',
        default=15,
        help='Default for users with policy = Use default settings. Custom users have their own value on the user form.',
    )
    ages_session_timeout_warning_seconds = fields.Integer(
        string='Default warning before logout (seconds)',
        config_parameter='ages_user_session_timeout.warning_seconds',
        default=60,
    )
    ages_session_timeout_max_hours = fields.Integer(
        string='Maximum session length (hours)',
        config_parameter='ages_user_session_timeout.max_session_hours',
        default=0,
        help='Force logout after this many hours even if the user is still active. 0 = no maximum. Applies to default and custom policies.',
    )
    ages_session_timeout_apply_internal = fields.Boolean(
        string='Internal users',
        config_parameter='ages_user_session_timeout.apply_internal',
        default=True,
    )
    ages_session_timeout_apply_portal = fields.Boolean(
        string='Portal users',
        config_parameter='ages_user_session_timeout.apply_portal',
        default=False,
    )
    ages_session_timeout_exclude_admins = fields.Boolean(
        string='Exclude Settings administrators',
        config_parameter='ages_user_session_timeout.exclude_admins',
        default=True,
    )
    ages_session_timeout_group_ids = fields.Many2many(
        'res.groups',
        'ages_session_timeout_settings_group_rel',
        'config_id',
        'group_id',
        string='Additional groups',
    )
    ages_session_timeout_user_ids = fields.Many2many(
        'res.users',
        'ages_session_timeout_settings_user_rel',
        'config_id',
        'user_id',
        string='Specific users (custom policy)',
        help='These users get Timeout Policy = Custom using the default minutes unless already set on the user form.',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        raw = self.env['ir.config_parameter'].sudo().get_param(PARAM_GROUP_IDS, '') or ''
        group_ids = [int(token) for token in raw.split(',') if token.strip().isdigit()]
        user_ids = self.env['res.users'].sudo().search([
            ('ages_timeout_policy', '=', 'custom'),
        ]).ids
        if not user_ids:
            user_ids = self.env['res.users'].sudo().search([
                ('ages_force_session_timeout', '=', True),
            ]).ids
        res['ages_session_timeout_group_ids'] = [(6, 0, group_ids)]
        res['ages_session_timeout_user_ids'] = [(6, 0, user_ids)]
        return res

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        group_ids = ','.join(str(gid) for gid in self.ages_session_timeout_group_ids.ids)
        params.set_param(PARAM_GROUP_IDS, group_ids)
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        selected = self.ages_session_timeout_user_ids
        previously = Users.search([('ages_timeout_policy', '=', 'custom')])
        (previously - selected).write({
            'ages_timeout_policy': 'default',
            'ages_force_session_timeout': False,
        })
        if selected:
            selected.write({
                'ages_timeout_policy': 'custom',
                'ages_force_session_timeout': True,
            })

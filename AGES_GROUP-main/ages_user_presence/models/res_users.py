# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import AccessError


class ResUsers(models.Model):
    _inherit = 'res.users'

    ages_presence_session_count = fields.Integer(
        string='Presence sessions',
        compute='_compute_ages_presence_session_count',
    )

    def _compute_ages_presence_session_count(self):
        counts = {}
        if self.ids:
            rows = self.env['ages.user.session'].sudo()._read_group(
                [('user_id', 'in', self.ids), ('is_logged_in', '=', True)],
                groupby=['user_id'],
                aggregates=['__count'],
            )
            counts = {user.id: count for user, count in rows}
        for user in self:
            user.ages_presence_session_count = counts.get(user.id, 0)

    def action_view_ages_presence_sessions(self):
        self.ensure_one()
        if not self.env.user.has_group('ages_user_presence.group_presence_monitor'):
            raise AccessError(_('You cannot open presence sessions.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Presence Sessions'),
            'res_model': 'ages.user.session',
            'view_mode': 'list,form',
            'domain': [('user_id', '=', self.id)],
            'context': {'search_default_logged_in': 1},
        }

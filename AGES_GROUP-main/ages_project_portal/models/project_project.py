# -*- coding: utf-8 -*-
import re
import string
import secrets
from odoo import api, fields, models, _

_CLIENT_SUFFIX_RE = re.compile(r'(?:\s*\|\s*CLIENT\s*\|?\s*)+$', re.IGNORECASE)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    portal_user_id = fields.Char(
        string='User ID',
        copy=False,
        help='Unique portal login User ID per project.',
    )
    portal_password = fields.Char(
        string='Password',
        copy=False,
        default=lambda self: self._generate_random_password(),
        help='Portal user login password.',
    )
    portal_link = fields.Char(
        string='Portal Link',
        compute='_compute_portal_link',
        help='Readonly link for portal access.',
    )
    portal_last_login = fields.Datetime(
        string='Last Login Time',
        readonly=True,
        copy=False,
    )
    portal_last_device = fields.Text(
        string='Last Device Details',
        readonly=True,
        copy=False,
    )
    portal_default_check_in = fields.Char(
        string='Default Check IN',
        default='08:00',
        help='Default shift start for portal attendance (HH:MM 24h).',
    )
    portal_default_check_out = fields.Char(
        string='Default Check OUT',
        default='17:00',
        help='Default shift end for portal attendance (HH:MM 24h).',
    )

    _sql_constraints = [
        (
            'portal_user_id_unique',
            'UNIQUE(portal_user_id)',
            'The Portal User ID must be unique per project!'
        )
    ]

    def ages_portal_display_name(self):
        """Portal label without the Odoo `| CLIENT |` suffix."""
        self.ensure_one()
        name = (self.name or '').strip()
        cleaned = _CLIENT_SUFFIX_RE.sub('', name).strip(' |')
        return cleaned or name

    @api.model
    def _generate_random_password(self, length=10):
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @api.depends()
    def _compute_portal_link(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', default='')
        link = f"{base_url.rstrip('/')}/project/portal/login"
        for rec in self:
            rec.portal_link = link

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('portal_password'):
                vals['portal_password'] = self._generate_random_password()
        return super().create(vals_list)

    def action_generate_portal_password(self):
        for rec in self:
            rec.portal_password = self._generate_random_password()

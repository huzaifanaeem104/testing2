# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    gate_pass_sub_company_ids = fields.Many2many(
        comodel_name='ages.sub.company',
        relation='res_users_gate_pass_sub_company_rel',
        column1='user_id',
        column2='sub_company_id',
        string='Allowed Active Companies (Gate Pass)',
        help='Restricts which Active Companies\' Gate Passes this user can '
             'see. Leave empty and the user will only see Gate Passes that '
             'have no Active Company set. Users in the Gate Pass Manager '
             'group are never restricted, regardless of this field.',
    )

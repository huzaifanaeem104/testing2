# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    je_stage = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('validate', 'Validation'),
            ('posted', 'Posted'),
        ],
        string='JE Stage',
        default='draft',
        copy=False,
        tracking=True,
        index=True,
        help='Custom Draft / Validation / Posted approval stage for Journal Entries.',
    )
    use_je_workflow = fields.Boolean(compute='_compute_use_je_workflow')
    can_draft_je = fields.Boolean(compute='_compute_je_access_rights')
    can_validate_je = fields.Boolean(compute='_compute_je_access_rights')
    can_post_je = fields.Boolean(compute='_compute_je_access_rights')

    @api.depends('move_type', 'origin_payment_id', 'statement_line_id')
    def _compute_use_je_workflow(self):
        for move in self:
            move.use_je_workflow = (
                move.move_type == 'entry'
                and not move.origin_payment_id
                and not move.statement_line_id
            )

    @api.depends_context('uid')
    def _compute_je_access_rights(self):
        user = self.env.user
        for move in self:
            move.can_draft_je = user.je_access_draft
            move.can_validate_je = user.je_access_validate
            move.can_post_je = user.je_access_post

    def _je_notify_users(self, access_field, message):
        self.ensure_one()
        users = self.env['res.users'].sudo().search([
            (access_field, '=', True),
            ('id', '!=', self.env.uid),
        ])
        for user in users:
            self.env['bus.bus']._sendone(
                user.partner_id,
                'simple_notification',
                {
                    'type': 'info',
                    'title': _('Journal Entry'),
                    'message': message,
                    'sticky': False,
                },
            )

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if move.use_je_workflow:
                move._je_notify_users(
                    'je_access_validate',
                    _('Journal entry %s is waiting for your validation.') % move.name,
                )
        return moves

    def action_je_validate(self):
        for move in self:
            if not move.use_je_workflow:
                continue
            if not self.env.user.je_access_validate:
                raise UserError(_('You are not allowed to validate journal entries.'))
            if move.je_stage != 'draft':
                raise UserError(_('Only entries in Draft can be validated.'))
            move.je_stage = 'validate'
            move._je_notify_users(
                'je_access_post',
                _('Journal entry %s is waiting to be posted.') % move.name,
            )

    def action_je_revoke_to_draft(self):
        for move in self:
            if not move.use_je_workflow:
                continue
            if not self.env.user.je_access_validate:
                raise UserError(_('You are not allowed to revoke journal entries.'))
            if move.je_stage != 'validate':
                raise UserError(_('Only entries in Validation can be revoked to Draft.'))
            move.je_stage = 'draft'
            move._je_notify_users(
                'je_access_draft',
                _('Journal entry %s was sent back to Draft for changes.') % move.name,
            )

    def action_je_post(self):
        for move in self:
            if not move.use_je_workflow:
                continue
            if not self.env.user.je_access_post:
                raise UserError(_('You are not allowed to post journal entries.'))
            if move.je_stage != 'validate':
                raise UserError(_('Only validated entries can be posted.'))
            move.action_post()
            move.je_stage = 'posted'

    def action_je_revoke_to_validate(self):
        for move in self:
            if not move.use_je_workflow:
                continue
            if not self.env.user.je_access_post:
                raise UserError(_('You are not allowed to revoke journal entries.'))
            if move.je_stage != 'posted':
                raise UserError(_('Only posted entries can be revoked to Validation.'))
            move.button_draft()
            move.je_stage = 'validate'
            move._je_notify_users(
                'je_access_validate',
                _('Journal entry %s was sent back for re-validation.') % move.name,
            )

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .dairy_milking_line import ENTRY_STATUS


class DairyMilkingCorrection(models.Model):
    """Audited correction of a cow record after the session was submitted/confirmed.

    The original values are kept on the correction; the line is only changed
    when a manager applies it, and every application is logged on the session.
    """
    _name = 'dairy.milking.correction'
    _description = 'Milking Correction'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    session_id = fields.Many2one('dairy.milking.session', required=True, index=True, ondelete='restrict',
                                 domain="[('state', 'in', ('submitted', 'confirmed'))]", check_company=True)
    line_id = fields.Many2one('dairy.milking.line', string='Cow Record', required=True, ondelete='restrict',
                              domain="[('session_id', '=', session_id)]")
    animal_id = fields.Many2one(related='line_id.animal_id', store=True)
    old_entry_status = fields.Selection(ENTRY_STATUS, readonly=True)
    old_quantity = fields.Float(readonly=True, digits=(16, 2))
    new_entry_status = fields.Selection(ENTRY_STATUS, required=True, default='recorded')
    new_quantity = fields.Float(digits=(16, 2))
    reason = fields.Text(required=True)
    state = fields.Selection([
        ('draft', 'Requested'),
        ('applied', 'Applied'),
        ('rejected', 'Rejected'),
    ], default='draft', required=True, tracking=True)
    requested_by_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True)
    applied_on = fields.Datetime(readonly=True)
    company_id = fields.Many2one(related='session_id.company_id', store=True)

    _sql_constraints = [
        ('new_quantity_positive', 'CHECK(new_quantity >= 0)', 'The corrected quantity cannot be negative.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dairy.milking.correction') or _('New')
            line = self.env['dairy.milking.line'].browse(vals.get('line_id'))
            vals['old_entry_status'] = line.entry_status
            vals['old_quantity'] = line.quantity_liters
        records = super().create(vals_list)
        for rec in records:
            if rec.line_id.session_id != rec.session_id:
                raise UserError(_('The cow record does not belong to session %s.', rec.session_id.name))
            if rec.session_id.state not in ('submitted', 'confirmed'):
                raise UserError(_('Corrections apply to submitted or confirmed sessions only; '
                                  'edit draft sessions directly.'))
        return records

    def write(self, vals):
        if any(rec.state != 'draft' for rec in self) and set(vals) - {'state', 'approved_by_id', 'applied_on'}:
            raise UserError(_('Applied or rejected corrections cannot be changed.'))
        return super().write(vals)

    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_('Applied or rejected corrections are part of the audit trail.'))
        return super().unlink()

    def action_apply(self):
        if not self.env.user.has_group('dairy_farm_core.group_dairy_manager'):
            raise AccessError(_('Only a Dairy Farm Manager can apply milking corrections.'))
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('%s has already been processed.', rec.name))
            rec.session_id._check_correction_allowed()
            line = rec.line_id
            if (line.entry_status, line.quantity_liters) != (rec.old_entry_status, rec.old_quantity):
                raise UserError(_('The cow record changed after %s was requested; create a new request.', rec.name))
            quantity = rec.new_quantity if rec.new_entry_status == 'recorded' else 0.0
            line.with_context(dairy_milking_correction=True).write({
                'entry_status': rec.new_entry_status,
                'quantity_liters': quantity,
            })
            rec.write({'state': 'applied', 'approved_by_id': self.env.uid, 'applied_on': fields.Datetime.now()})
            rec.session_id.message_post(body=_(
                'Correction %(ref)s applied to %(animal)s: %(old)s L (%(old_s)s) → %(new)s L (%(new_s)s). Reason: %(reason)s',
                ref=rec.name, animal=line.animal_id.display_name,
                old=rec.old_quantity, old_s=rec.old_entry_status,
                new=quantity, new_s=rec.new_entry_status, reason=rec.reason))
        return True

    def action_reject(self):
        if not self.env.user.has_group('dairy_farm_core.group_dairy_manager'):
            raise AccessError(_('Only a Dairy Farm Manager can reject milking corrections.'))
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('%s has already been processed.', rec.name))
        self.write({'state': 'rejected', 'approved_by_id': self.env.uid})
        return True

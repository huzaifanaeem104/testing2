from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DairyShift(models.Model):
    _name = 'dairy.shift'
    _description = 'Farm Shift'
    _order = 'sequence, start_time'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Selection([
        ('morning', 'Morning'),
        ('afternoon', 'Afternoon'),
        ('evening', 'Evening'),
        ('other', 'Other'),
    ], required=True, default='other')
    sequence = fields.Integer(default=10)
    start_time = fields.Float(required=True, help='Planned start time (24h).')
    end_time = fields.Float(required=True, help='Planned end time (24h).')
    is_milking = fields.Boolean(string='Milking Shift', default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'Shift names must be unique per company.'),
    ]

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for shift in self:
            if not (0 <= shift.start_time < 24 and 0 <= shift.end_time <= 24):
                raise ValidationError(_('Shift times must be between 00:00 and 24:00.'))
            if shift.end_time <= shift.start_time:
                raise ValidationError(_('Shift "%s" must end after it starts.', shift.name))

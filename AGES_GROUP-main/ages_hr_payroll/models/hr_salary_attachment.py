# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrSalaryAttachment(models.Model):
    _name = 'hr.salary.attachment'
    _description = 'Salary Attachment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(required=True, tracking=True)
    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    other_input_type_id = fields.Many2one(
        'hr.payslip.input.type', string='Type', required=True,
        domain=[('available_in_attachments', '=', True)])
    monthly_amount = fields.Monetary(required=True)
    total_amount = fields.Monetary(help="Leave empty for unlimited / recurring.")
    paid_amount = fields.Monetary(compute='_compute_paid_amount', store=True)
    remaining_amount = fields.Monetary(compute='_compute_paid_amount', store=True)
    date_start = fields.Date(required=True, default=fields.Date.today)
    date_estimated_end = fields.Date()
    date_end = fields.Date()
    state = fields.Selection([
        ('open', 'Running'),
        ('close', 'Completed'),
        ('cancel', 'Cancelled'),
    ], default='open', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    description = fields.Text()
    payslip_ids = fields.Many2many('hr.payslip', relation='hr_payslip_hr_salary_attachment_rel')

    @api.depends('payslip_ids', 'payslip_ids.state', 'payslip_ids.line_ids.total', 'monthly_amount', 'total_amount')
    def _compute_paid_amount(self):
        for attachment in self:
            paid = 0.0
            code = attachment.other_input_type_id.code
            for slip in attachment.payslip_ids.filtered(lambda s: s.state in ('done', 'paid')):
                paid += abs(sum(slip.line_ids.filtered(lambda l: l.code == code).mapped('total')))
            attachment.paid_amount = paid
            if attachment.total_amount:
                attachment.remaining_amount = max(attachment.total_amount - paid, 0.0)
            else:
                attachment.remaining_amount = 0.0

    def action_done(self):
        self.write({'state': 'close', 'date_end': fields.Date.today()})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_open(self):
        self.write({'state': 'open', 'date_end': False})

    def _get_active_amount(self):
        self.ensure_one()
        if self.total_amount:
            return min(self.monthly_amount, self.remaining_amount or self.monthly_amount)
        return self.monthly_amount

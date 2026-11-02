# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import fields, models, _


class HrPayrollPaymentReportWizard(models.TransientModel):
    _name = 'hr.payroll.payment.report.wizard'
    _description = 'Payroll Payment Report Wizard'

    payslip_run_id = fields.Many2one('hr.payslip.run')
    payslip_ids = fields.Many2many('hr.payslip', string='Payslips')
    export_format = fields.Selection([('csv', 'CSV')], default='csv', required=True)

    def generate_payment_report(self):
        self.ensure_one()
        slips = self.payslip_ids or self.payslip_run_id.slip_ids
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['Employee', 'Reference', 'Net', 'Currency', 'Bank Account'])
        for slip in slips:
            bank = slip.employee_id.bank_account_id.acc_number if slip.employee_id.bank_account_id else ''
            writer.writerow([
                slip.employee_id.name,
                slip.number or '',
                slip.net_wage,
                slip.currency_id.name or '',
                bank,
            ])
        data = base64.b64encode(buffer.getvalue().encode('utf-8'))
        filename = 'payment_report.csv'
        if self.payslip_run_id:
            self.payslip_run_id.write({
                'payment_report': data,
                'payment_report_filename': filename,
                'payment_report_date': fields.Date.today(),
            })
        else:
            slips.write({
                'payment_report': data,
                'payment_report_filename': filename,
                'payment_report_date': fields.Date.today(),
            })
        return {'type': 'ir.actions.act_window_close'}

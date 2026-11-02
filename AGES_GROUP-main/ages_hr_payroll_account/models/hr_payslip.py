# -*- coding: utf-8 -*-
from collections import defaultdict
from markupsafe import Markup

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, plaintext2html


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    date = fields.Date(
        'Date Account',
        help="Keep empty to use the end of the payslip period.")
    journal_id = fields.Many2one(
        'account.journal', 'Salary Journal', related="struct_id.journal_id", check_company=True)
    move_id = fields.Many2one('account.move', 'Accounting Entry', readonly=True, copy=False)
    move_state = fields.Selection(related='move_id.state', string='Move State')
    batch_payroll_move_lines = fields.Boolean(related='company_id.batch_payroll_move_lines')

    def action_payslip_cancel(self):
        moves = self.mapped('move_id')
        moves.filtered(lambda m: m.state != 'draft').button_draft()
        moves.unlink()
        return super().action_payslip_cancel()

    def action_payslip_done(self):
        if any(slip.state == 'paid' for slip in self):
            raise ValidationError(_("You can't create a journal entry for a paid payslip."))
        res = super().action_payslip_done()
        self._action_create_account_move()
        return res

    def _action_create_account_move(self):
        precision = self.env['decimal.precision'].precision_get('Payroll')
        all_payslips = self
        for run in self.payslip_run_id:
            if run._are_payslips_ready():
                all_payslips |= run.slip_ids
        payslips_to_post = all_payslips.filtered(
            lambda slip: slip.state == 'done' and not slip.move_id and slip.struct_id.journal_id)
        if any(not payslip.struct_id for payslip in payslips_to_post):
            raise ValidationError(_('One of the contracts for these payslips has no structure.'))

        if self.company_id.batch_payroll_move_lines:
            all_slip_mapped_data = [defaultdict(lambda: defaultdict(lambda: self.env['hr.payslip']))]
            for slip in payslips_to_post:
                all_slip_mapped_data[0][slip.struct_id.journal_id.id][
                    slip.date or fields.Date.end_of(slip.date_to, 'month')] |= slip
        else:
            all_slip_mapped_data = [{
                slip.struct_id.journal_id.id: {
                    slip.date or fields.Date.end_of(slip.date_to, 'month'): slip
                }
            } for slip in payslips_to_post]

        account_move_vals = []
        slips_date_tuples = []
        for slip_mapped_data in all_slip_mapped_data:
            for journal_id in slip_mapped_data:
                for slip_date in slip_mapped_data[journal_id]:
                    line_ids = []
                    debit_sum = 0.0
                    credit_sum = 0.0
                    date = slip_date
                    move_dict = {
                        'narration': '',
                        'ref': fields.Date.end_of(
                            slip_mapped_data[journal_id][slip_date][0].date_to, 'month'
                        ).strftime('%B %Y'),
                        'journal_id': journal_id,
                        'date': date,
                    }
                    for slip in slip_mapped_data[journal_id][slip_date]:
                        move_dict['narration'] += plaintext2html(
                            (slip.number or '') + ' - ' + (slip.employee_id.name or ''))
                        move_dict['narration'] += Markup('<br/>')
                        slip_lines = slip._prepare_slip_lines(date, line_ids)
                        line_ids.extend(slip_lines)
                    for line_id in line_ids:
                        debit_sum += line_id['debit']
                        credit_sum += line_id['credit']
                    if float_compare(credit_sum, debit_sum, precision_digits=precision) == -1:
                        slip._prepare_adjust_line(line_ids, 'credit', debit_sum, credit_sum, date)
                    elif float_compare(debit_sum, credit_sum, precision_digits=precision) == -1:
                        slip._prepare_adjust_line(line_ids, 'debit', debit_sum, credit_sum, date)
                    move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
                    account_move_vals.append(move_dict)
                    slips_date_tuples.append((slip_mapped_data[journal_id][slip_date], date))
        moves = self._create_account_move(account_move_vals)
        for move, (slips, date) in zip(moves, slips_date_tuples):
            slips.write({'move_id': move.id, 'date': date})
            if slips.company_id.batch_payroll_move_lines:
                slips.payslip_run_id.write({'move_id': move.id})
        return True

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        partner = self.employee_id.work_contact_id if (
            not self.company_id.batch_payroll_move_lines and line.code == "NET"
        ) else line.partner_id
        analytic = False
        if line.salary_rule_id.analytic_account_id:
            analytic = {line.salary_rule_id.analytic_account_id.id: 100}
        return {
            'name': line.name if line.salary_rule_id.split_move_lines else line.salary_rule_id.name,
            'partner_id': partner.id if partner else False,
            'account_id': account_id,
            'debit': debit,
            'credit': credit,
            'analytic_distribution': analytic,
        }

    def _prepare_slip_lines(self, date, line_ids):
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Payroll')
        new_lines = []
        for line in self.line_ids.filtered(lambda line: line.category_id):
            amount = line.total
            if line.code == 'NET':
                for tmp_line in self.line_ids.filtered(lambda l: l.category_id):
                    if tmp_line.salary_rule_id.not_computed_in_net:
                        amount -= abs(tmp_line.total) if amount > 0 else -abs(tmp_line.total)
            if float_is_zero(amount, precision_digits=precision):
                continue
            debit_account_id = line.salary_rule_id.account_debit.id
            credit_account_id = line.salary_rule_id.account_credit.id
            if debit_account_id:
                debit = amount if amount > 0.0 else 0.0
                credit = -amount if amount < 0.0 else 0.0
                debit_line = next(self._get_existing_lines(
                    line_ids + new_lines, line, debit_account_id, debit, credit), False)
                if not debit_line:
                    new_lines.append(self._prepare_line_values(line, debit_account_id, date, debit, credit))
                else:
                    debit_line['debit'] += debit
                    debit_line['credit'] += credit
            if credit_account_id:
                debit = -amount if amount < 0.0 else 0.0
                credit = amount if amount > 0.0 else 0.0
                credit_line = next(self._get_existing_lines(
                    line_ids + new_lines, line, credit_account_id, debit, credit), False)
                if not credit_line:
                    new_lines.append(self._prepare_line_values(line, credit_account_id, date, debit, credit))
                else:
                    credit_line['debit'] += debit
                    credit_line['credit'] += credit
        return new_lines

    def _prepare_adjust_line(self, line_ids, adjust_type, debit_sum, credit_sum, date):
        acc_id = self.sudo().journal_id.default_account_id.id
        if not acc_id:
            raise UserError(_('The Expense Journal "%s" has not properly configured the default Account!', self.journal_id.name))
        adjust_credit = next(
            (line_id for line_id in line_ids if line_id['name'] == _('Adjustment Entry')), False)
        if not adjust_credit:
            line_ids.append({
                'name': _('Adjustment Entry'),
                'partner_id': False,
                'account_id': acc_id,
                'debit': 0.0 if adjust_type == 'credit' else credit_sum - debit_sum,
                'credit': debit_sum - credit_sum if adjust_type == 'credit' else 0.0,
            })
        else:
            adjust_credit['credit'] = debit_sum - credit_sum

    def _get_existing_lines(self, line_ids, line, account_id, debit, credit):
        existing = (
            line_id for line_id in line_ids if
            line_id['name'] == (line.name if line.salary_rule_id.split_move_lines else line.salary_rule_id.name)
            and line_id['account_id'] == account_id
            and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0))
            and line_id.get('partner_id') == (
                self.employee_id.work_contact_id.id
                if (not self.company_id.batch_payroll_move_lines and line.code == "NET")
                else (line.partner_id.id if line.partner_id else False)
            )
        )
        return existing

    def _create_account_move(self, account_move_vals):
        return self.env['account.move'].sudo().create(account_move_vals)

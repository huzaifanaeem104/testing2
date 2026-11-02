# -*- coding: utf-8 -*-
from odoo import api, models, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_loan_advance_input_types(self):
        InputType = self.env['hr.payslip.input.type']
        return {
            'ADVANCE': InputType.search([('code', '=', 'ADVANCE')], limit=1),
            'LOAN': InputType.search([('code', '=', 'LOAN')], limit=1),
        }

    def _prepare_advance_input_lines(self):
        self.ensure_one()
        lines = []
        input_types = self._get_loan_advance_input_types()
        advance_type = input_types.get('ADVANCE')
        if not advance_type or not self.employee_id or not self.date_from or not self.date_to:
            return lines
        advances = self.env['hr.advance.application'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'confirmed'),
            ('deduction_state', 'in', ('pending', 'partial', 'skipped')),
            ('skip_next_payslip', '=', False),
            '|', ('recovery_date', '=', False), ('recovery_date', '<=', self.date_to),
        ])
        for advance in advances:
            amount = advance._get_pending_amount_for_payslip(self)
            if amount <= 0:
                continue
            lines.append({
                'name': _('Advance %s') % advance.name,
                'input_type_id': advance_type.id,
                'amount': amount,
                'advance_id': advance.id,
            })
        return lines

    def _prepare_loan_input_lines(self):
        self.ensure_one()
        lines = []
        input_types = self._get_loan_advance_input_types()
        loan_type = input_types.get('LOAN')
        if not loan_type or not self.employee_id or not self.date_from or not self.date_to:
            return lines
        installments = self.env['hr.loan.installment'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('loan_id.state', '=', 'confirmed'),
            ('deduction_state', 'in', ('pending', 'partial', 'skipped')),
            ('skip_next_payslip', '=', False),
            ('due_date', '<=', self.date_to),
        ])
        for installment in installments:
            amount = installment._get_pending_amount_for_payslip(self)
            if amount <= 0:
                continue
            lines.append({
                'name': installment.name,
                'input_type_id': loan_type.id,
                'amount': amount,
                'loan_installment_id': installment.id,
            })
        return lines

    @api.depends(
        'employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to',
        'struct_id.input_line_type_ids', 'salary_attachment_ids',
    )
    def _compute_input_line_ids(self):
        super()._compute_input_line_ids()
        for slip in self:
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                continue
            new_vals = slip._prepare_advance_input_lines() + slip._prepare_loan_input_lines()
            other_lines = []
            for line in slip.input_line_ids:
                # Drop previous advance/loan linked lines and empty ADVANCE/LOAN placeholders
                # (placeholders are replaced by linked lines when pending recoveries exist).
                if line.advance_id or line.loan_installment_id:
                    continue
                if line.code in ('ADVANCE', 'LOAN'):
                    if not new_vals:
                        other_lines.append((4, line.id))
                    continue
                other_lines.append((4, line.id))
            new_lines = [(0, 0, vals) for vals in new_vals]
            if new_lines or any(l.advance_id or l.loan_installment_id for l in slip.input_line_ids):
                slip.update({'input_line_ids': [(5, 0, 0)] + other_lines + new_lines})

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._loan_advance_mark_deducted()
        return res

    def action_payslip_cancel(self):
        self._loan_advance_reopen_deductions()
        return super().action_payslip_cancel()

    def action_payslip_draft(self):
        self._loan_advance_reopen_deductions()
        return super().action_payslip_draft()

    def _loan_advance_mark_deducted(self):
        advances = self.env['hr.advance.application']
        installments = self.env['hr.loan.installment']
        for slip in self:
            for line in slip.input_line_ids.filtered(lambda l: l.advance_id):
                advances |= line.advance_id
            for line in slip.input_line_ids.filtered(lambda l: l.loan_installment_id):
                inst = line.loan_installment_id
                inst.payslip_id = slip.id
                installments |= inst
        advances.write({'skip_next_payslip': False})
        installments.write({'skip_next_payslip': False})
        advances.invalidate_recordset(['amount_deducted', 'amount_residual'])
        advances._compute_deduction_amounts()
        advances._update_deduction_state_from_amounts()
        installments.invalidate_recordset(['amount_deducted', 'amount_residual'])
        installments._compute_deduction()
        installments._update_deduction_state_from_amounts()

    def _loan_advance_reopen_deductions(self):
        advances = self.env['hr.advance.application']
        installments = self.env['hr.loan.installment']
        for slip in self:
            for line in slip.input_line_ids.filtered(lambda l: l.advance_id):
                advances |= line.advance_id
            for line in slip.input_line_ids.filtered(lambda l: l.loan_installment_id):
                inst = line.loan_installment_id
                if inst.payslip_id == slip:
                    inst.payslip_id = False
                installments |= inst
        advances.invalidate_recordset(['amount_deducted', 'amount_residual'])
        advances._compute_deduction_amounts()
        advances._update_deduction_state_from_amounts()
        installments.invalidate_recordset(['amount_deducted', 'amount_residual'])
        installments._compute_deduction()
        installments._update_deduction_state_from_amounts()

    def write(self, vals):
        track_removal = 'input_line_ids' in vals and not self.env.context.get('loan_advance_skip_track')
        before_adv = {}
        before_loan = {}
        if track_removal:
            for slip in self:
                before_adv[slip.id] = {
                    line.id: line.advance_id
                    for line in slip.input_line_ids if line.advance_id
                }
                before_loan[slip.id] = {
                    line.id: line.loan_installment_id
                    for line in slip.input_line_ids if line.loan_installment_id
                }
        res = super().write(vals)
        if track_removal:
            removed_advances = self.env['hr.advance.application']
            removed_installments = self.env['hr.loan.installment']
            for slip in self:
                after_ids = set(slip.input_line_ids.ids)
                for line_id, advance in before_adv.get(slip.id, {}).items():
                    if line_id not in after_ids and advance:
                        removed_advances |= advance
                for line_id, installment in before_loan.get(slip.id, {}).items():
                    if line_id not in after_ids and installment:
                        removed_installments |= installment
            if removed_advances:
                removed_advances.action_mark_skipped()
            if removed_installments:
                removed_installments.action_mark_skipped()
        return res

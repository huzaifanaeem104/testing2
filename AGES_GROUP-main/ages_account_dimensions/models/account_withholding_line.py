# -*- coding: utf-8 -*-

from odoo import Command, api, models


class AccountWithholdingLine(models.AbstractModel):
    _inherit = 'account.withholding.line'

    @api.model
    def _ages_account_from_tax(self, tax):
        """GL account configured on a withholding tax (invoice tax repartition)."""
        if not tax:
            return self.env['account.account']
        tax_reps = tax.repartition_line_ids.filtered(
            lambda line: line.repartition_type == 'tax' and line.account_id
        )
        if not tax_reps:
            tax_reps = (
                tax.invoice_repartition_line_ids | tax.refund_repartition_line_ids
            ).filtered(lambda line: line.repartition_type == 'tax' and line.account_id)
        preferred = tax_reps.filtered(lambda line: line.document_type == 'invoice')
        chosen = preferred[:1] or tax_reps[:1]
        if chosen:
            return chosen.account_id
        group = tax.tax_group_id
        if group:
            if tax.type_tax_use == 'sale' and group.tax_receivable_account_id:
                return group.tax_receivable_account_id
            if group.tax_payable_account_id:
                return group.tax_payable_account_id
            if group.tax_receivable_account_id:
                return group.tax_receivable_account_id
        return self.env['account.account']

    def _ages_get_default_withholding_account(self):
        self.ensure_one()
        return (
            self._ages_account_from_tax(self.tax_id)
            or self.company_id.withholding_tax_base_account_id
        )

    @api.depends('company_id', 'tax_id')
    def _compute_account_id(self):
        for line in self:
            account = line._ages_get_default_withholding_account()
            if account:
                line.account_id = account
            else:
                line.account_id = line.account_id or False

    @api.onchange('tax_id')
    def _onchange_tax_id_ages_account(self):
        for line in self:
            account = line._ages_get_default_withholding_account()
            if account:
                line.account_id = account

    def _ages_format_wht_tax_percent(self, tax):
        amount = abs(tax.amount or 0.0) if tax else 0.0
        if abs(amount - round(amount)) < 0.005:
            return '%d' % int(round(amount))
        return ('%.2f' % amount).rstrip('0').rstrip('.')

    def _ages_wht_tax_label(self, aml_vals):
        tax = self.env['account.tax']
        rep_id = aml_vals.get('tax_repartition_line_id')
        if rep_id:
            tax = self.env['account.tax.repartition.line'].browse(rep_id).tax_id
        if not tax:
            taxes = self.mapped('tax_id')
            if len(taxes) == 1:
                tax = taxes
        percent = self._ages_format_wht_tax_percent(tax)
        return self.env._('WTH Tax: %s%%') % percent

    def _ages_is_wh_tax_label(self, name):
        name = name or ''
        translated = self.env._('WH Tax: %(name)s', name='')
        prefix = translated.split('%')[0].strip() or 'WH Tax:'
        return name.startswith('WH Tax:') or name.startswith(prefix) or name.startswith('WTH Tax:')

    def _prepare_withholding_amls_create_values(self):
        """Keep only the WTH Tax amount lines and label them with the tax %."""
        aml_create_values_list = super()._prepare_withholding_amls_create_values()
        base_prefix = self.env._('WH Base: %(names)s', names='').rstrip()
        counterpart_prefix = self.env._('WH Base Counterpart: %(names)s', names='').rstrip()
        result = []
        for vals in aml_create_values_list:
            name = vals.get('name') or ''
            if name.startswith(base_prefix) or name.startswith(counterpart_prefix):
                continue
            if self._ages_is_wh_tax_label(name):
                vals = dict(vals, name=self._ages_wht_tax_label(vals))
            result.append(vals)
        return result

    def _prepare_withholding_lines_commands(self, base_lines, company):
        """Put each tax's GL account on auto-created withholding lines."""
        commands = super()._prepare_withholding_lines_commands(base_lines, company)
        for command in commands:
            if command[0] != Command.CREATE:
                continue
            vals = command[2]
            tax = self.env['account.tax'].browse(vals.get('tax_id'))
            account = (
                self._ages_account_from_tax(tax)
                or company.withholding_tax_base_account_id
            )
            if account:
                vals['account_id'] = account.id
        return commands

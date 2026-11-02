# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class AccountWithholdingLine(models.AbstractModel):
    """ Inherit account.withholding.line to auto-populate sequence, account and base amount """
    
    _inherit = 'account.withholding.line'

    # Add a field to store the sequence code
    withholding_sequence_code = fields.Char(
        string='Sequence Code',
        default='account.withholding.line.sequence',
        help='Sequence code used for auto-generating withholding line numbers'
    )

    @api.model_create_multi
    def create(self, vals_list):
        """ Override create to auto-assign sequence number to name field """
        # Get the sequence code from context or use default
        sequence_code = self.env.context.get('withholding_sequence_code', 'account.withholding.line.sequence')
        
        for vals in vals_list:
            # Only assign name if it's not already set
            if not vals.get('name'):
                # Try to get sequence by code (this is the recommended way)
                name = self.env['ir.sequence'].next_by_code(sequence_code)
                if not name:
                    # Fallback: search for sequence and use next_by_id
                    sequence = self.env['ir.sequence'].search([('code', '=', sequence_code)], limit=1)
                    if sequence:
                        name = sequence.next_by_id()
                    else:
                        # Last fallback: try default code
                        name = self.env['ir.sequence'].next_by_code('account.withholding.line.sequence')
                        if not name:
                            # If still no sequence, create a simple number
                            # This should not happen if sequence is properly configured
                            name = 'WH-001'
                vals['name'] = name
        
        return super().create(vals_list)

    @api.model
    def _auto_account_from_tax(self, tax):
        """GL account configured on a withholding tax (tax repartition, not base)."""
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

    @api.depends('company_id', 'tax_id')
    def _compute_account_id(self):
        """Always assign Account: tax GL account, else company withholding default."""
        for line in self:
            account = self._auto_account_from_tax(line.tax_id)
            if not account:
                account = line.company_id.withholding_tax_base_account_id
            line.account_id = account or line.account_id or False

    @api.depends('original_base_amount', 'comodel_percentage_paid_factor')
    def _compute_base_amount(self):
        """ Override to get base_amount from payment register or standalone payment amount """
        super()._compute_base_amount()
        
        for line in self:
            if line.base_amount and line.base_amount > 0:
                continue
            amount = 0.0
            currency = None
            parent = line._get_payment_register_record() or line._get_payment_record()
            if not parent:
                continue
            # Amount from parent (register or payment)
            if hasattr(parent, 'amount') and parent.amount:
                amount = parent.amount
            elif hasattr(parent, 'payment_amount') and parent.payment_amount:
                amount = parent.payment_amount
            elif hasattr(parent, 'source_amount') and parent.source_amount:
                amount = parent.source_amount
            elif hasattr(parent, 'source_amount_currency') and parent.source_amount_currency:
                amount = parent.source_amount_currency
            if not amount or amount <= 0:
                continue
            if hasattr(parent, 'currency_id') and parent.currency_id:
                currency = parent.currency_id
            elif hasattr(parent, 'source_currency_id') and parent.source_currency_id:
                currency = parent.source_currency_id
            elif hasattr(parent, 'company_id') and parent.company_id:
                currency = parent.company_id.currency_id
            if currency and line.comodel_currency_id and currency != line.comodel_currency_id:
                rate = self.env['res.currency']._get_conversion_rate(
                    from_currency=currency,
                    to_currency=line.comodel_currency_id,
                    company=line.company_id,
                    date=line.comodel_date or fields.Date.today(),
                )
                amount = amount * rate
            if line.comodel_currency_id:
                line.base_amount = line.comodel_currency_id.round(amount)

    def _get_payment_register_record(self):
        """ Helper method to get the payment register record (parent) """
        self.ensure_one()
        
        # Method 1: Try to get from active_id in context (most common when adding lines from form)
        if 'active_id' in self.env.context and 'active_model' in self.env.context:
            active_model = self.env.context.get('active_model')
            active_id = self.env.context.get('active_id')
            if active_model == 'account.payment.register' and active_id:
                return self.env['account.payment.register'].browse(active_id)
        
        # Method 2: Try to get from default_parent_id in context
        if 'default_parent_id' in self.env.context:
            parent_id = self.env.context.get('default_parent_id')
            if parent_id:
                return self.env['account.payment.register'].browse(parent_id)
        
        # Method 3: Search for account.payment.register records that contain this line
        # This works if the line is already saved and linked
        if self.id:
            payment_register = self.env['account.payment.register'].search([
                ('withholding_line_ids', 'in', self.ids)
            ], limit=1)
            if payment_register:
                return payment_register
        
        # Method 4: Check if there's a parent_id field (if defined in child model)
        if hasattr(self, 'parent_id') and self.parent_id:
            if self.parent_id._name == 'account.payment.register':
                return self.parent_id
        
        return False

    def _get_payment_record(self):
        """ Helper to get the standalone account.payment record (parent) when not from register """
        self.ensure_one()
        # Method 1: context when adding lines from payment form
        if 'active_id' in self.env.context and 'active_model' in self.env.context:
            active_model = self.env.context.get('active_model')
            active_id = self.env.context.get('active_id')
            if active_model == 'account.payment' and active_id:
                return self.env['account.payment'].browse(active_id)
        # Method 2: parent field (payment_id, wizard_id, etc.)
        for field_name in ('payment_id', 'wizard_id', 'parent_id', 'register_id'):
            if hasattr(self, field_name):
                parent = getattr(self, field_name, False)
                if parent and parent._name == 'account.payment':
                    return parent
        # Method 3: default from context
        for ctx_key in ('default_payment_id', 'default_parent_id'):
            if ctx_key in self.env.context:
                pay_id = self.env.context.get(ctx_key)
                if pay_id:
                    return self.env['account.payment'].browse(pay_id)
        # Method 4: search account.payment that contains this line
        if self.id:
            Payment = self.env['account.payment']
            for field in ('withholding_line_ids', 'payment_withholding_line_ids'):
                if hasattr(Payment, field):
                    payment = Payment.search([(field, 'in', self.ids)], limit=1)
                    if payment:
                        return payment
        return False

    @api.onchange('tax_id')
    def _onchange_tax_id_payment_account_and_base(self):
        """ When tax is selected: set account from tax and base_amount from parent (payment or register). """
        if not self.tax_id:
            return
        account = self._auto_account_from_tax(self.tax_id)
        if not account:
            account = self.company_id.withholding_tax_base_account_id
        if account:
            self.account_id = account
        # Base amount from parent (payment or register) when empty
        if self.base_amount and self.base_amount > 0:
            return
        parent = self._get_payment_register_record() or self._get_payment_record()
        if not parent:
            return
        amount = 0.0
        if hasattr(parent, 'amount') and parent.amount:
            amount = parent.amount
        elif hasattr(parent, 'payment_amount') and parent.payment_amount:
            amount = parent.payment_amount
        elif hasattr(parent, 'source_amount') and parent.source_amount:
            amount = parent.source_amount
        elif hasattr(parent, 'source_amount_currency') and parent.source_amount_currency:
            amount = parent.source_amount_currency
        if amount and amount > 0 and getattr(self, 'comodel_currency_id', None):
            currency = None
            if hasattr(parent, 'currency_id') and parent.currency_id:
                currency = parent.currency_id
            elif hasattr(parent, 'source_currency_id') and parent.source_currency_id:
                currency = parent.source_currency_id
            elif hasattr(parent, 'company_id') and parent.company_id:
                currency = parent.company_id.currency_id
            if currency and currency != self.comodel_currency_id:
                rate = self.env['res.currency']._get_conversion_rate(
                    from_currency=currency,
                    to_currency=self.comodel_currency_id,
                    company=self.company_id,
                    date=getattr(self, 'comodel_date', None) or fields.Date.today(),
                )
                amount = amount * rate
            self.base_amount = self.comodel_currency_id.round(amount)


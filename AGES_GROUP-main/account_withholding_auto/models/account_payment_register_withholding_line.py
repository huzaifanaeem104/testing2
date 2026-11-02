# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class AccountPaymentRegisterWithholdingLine(models.TransientModel):
    """ Inherit account.payment.register.withholding.line to auto-populate sequence, account and base amount """

    _inherit = 'account.payment.register.withholding.line'

    def _get_wizard_for_sequence(self):
        """Get parent wizard (account.payment.register) from this line."""
        for field_name in ('wizard_id', 'payment_register_id', 'parent_id', 'register_id'):
            if hasattr(self, field_name):
                parent = getattr(self, field_name, False)
                if parent and parent._name == 'account.payment.register':
                    return parent
        return self.env['account.payment.register']

    @api.model
    def _next_sequence_for_register(self, wizard):
        """Return next sequence number (0, 1, 2...) for wizard's withholding lines (same logic as account.payment.withholding.line)."""
        if not wizard or not wizard.exists() or not hasattr(wizard, 'withholding_line_ids'):
            return '0'
        return str(len(wizard.withholding_line_ids))

    @api.model
    def _get_payment_register_from_vals(self, vals):
        """Get account.payment.register from vals first, then context (same pattern as account.payment.withholding.line)."""
        vals = vals or {}
        Register = self.env['account.payment.register']
        for fname in ('wizard_id', 'parent_id', 'payment_register_id', 'register_id'):
            wid = vals.get(fname)
            if wid:
                w = Register.browse(wid)
                if w.exists():
                    return w
        for key in ('default_parent_id', 'default_wizard_id', 'default_payment_register_id'):
            wid = self.env.context.get(key)
            if wid:
                return Register.browse(wid)
        return self._get_payment_register_from_context()

    def _assign_number_from_position(self):
        """ Assign number based on line's position in parent's withholding_line_ids (0, 1, 2...). """
        try:
            payment_register = self._get_payment_register_wizard()
        except Exception:
            payment_register = False

        if payment_register and hasattr(payment_register, 'withholding_line_ids'):
            all_lines = payment_register.withholding_line_ids
            saved_lines = [l for l in all_lines if l.id and isinstance(l.id, int)]
            new_lines = [l for l in all_lines if not l.id or not isinstance(l.id, int)]
            if self.id and isinstance(self.id, int):
                saved_lines = [l for l in saved_lines if l.id != self.id]
            else:
                new_lines = [l for l in new_lines if l != self]
            saved_lines_sorted = sorted(saved_lines, key=lambda x: x.id) if saved_lines else []
            if self.id and isinstance(self.id, int):
                try:
                    position = [l.id for l in saved_lines_sorted].index(self.id)
                    return str(position)
                except (ValueError, AttributeError):
                    pass
            total_count = len(saved_lines_sorted) + len(new_lines)
            return str(total_count)
        return '0'

    @api.model
    def _get_payment_register_from_context(self):
        """Get account.payment.register from context (wizard may be opened from bill, so active_model can be account.move)."""
        ctx = self.env.context
        if ctx.get('active_model') == 'account.payment.register' and ctx.get('active_id'):
            return self.env['account.payment.register'].browse(ctx['active_id'])
        for key in ('default_parent_id', 'default_wizard_id', 'default_payment_register_id'):
            if ctx.get(key):
                return self.env['account.payment.register'].browse(ctx[key])
        move_ids = []
        line_ids = []
        Register = self.env['account.payment.register']
        if ctx.get('active_model') == 'account.move' and (ctx.get('active_id') or ctx.get('active_ids')):
            move_ids = list(ctx.get('active_ids') or [ctx.get('active_id')])
        elif ctx.get('active_model') == 'account.move.line' and (ctx.get('active_id') or ctx.get('active_ids')):
            line_ids = list(ctx.get('active_ids') or [ctx.get('active_id')])
            lines = self.env['account.move.line'].browse(line_ids)
            move_ids = lines.mapped('move_id').ids
            reg = Register.search([('create_uid', '=', self.env.uid)], limit=1, order='id desc')
            if reg:
                return reg
        if move_ids:
            for domain in (
                    [('line_ids.move_id', 'in', move_ids)],
                    [('source_move_ids', 'in', move_ids)],
                    [('move_id', 'in', move_ids)],
            ):
                try:
                    reg = Register.search(domain, limit=1, order='id desc')
                    if reg:
                        return reg
                except Exception:
                    continue
            if line_ids:
                try:
                    reg = Register.search([('line_ids', 'in', line_ids)], limit=1, order='id desc')
                    if reg:
                        return reg
                except Exception:
                    pass
            try:
                from datetime import datetime, timedelta
                recent = datetime.now() - timedelta(minutes=5)
                reg = Register.search([
                    ('create_uid', '=', self.env.uid),
                    ('create_date', '>=', recent),
                ], limit=1, order='id desc')
                if reg:
                    return reg
            except Exception:
                pass
            reg = Register.search([], limit=1, order='id desc')
            if reg:
                return reg
        return self.env['account.payment.register']

    @api.model
    def default_get(self, fields_list):
        """ Set default counter number 0, 1, 2... when adding a line (same logic as account.payment.withholding.line). """
        res = super().default_get(fields_list)
        if res.get('name'):
            return res
        wizard = self._get_payment_register_from_vals(res)
        if wizard and wizard.exists():
            res['name'] = self._next_sequence_for_register(wizard)
        else:
            res['name'] = '0'
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """ Assign name 0, 1, 2... when new lines are created (same logic as account.payment.withholding.line). """
        if not vals_list:
            return super().create(vals_list)
        wizard = self._get_payment_register_from_vals(vals_list[0])
        if wizard and wizard.exists() and hasattr(wizard, 'withholding_line_ids'):
            # Count only saved lines (real IDs), same as account.payment.withholding.line
            existing_count = len(
                wizard.withholding_line_ids.filtered(
                    lambda l: l.id and isinstance(l.id, int)
                )
            )
            for index, vals in enumerate(vals_list):
                if not vals.get('name'):
                    vals['name'] = str(existing_count + index)
        else:
            for index, vals in enumerate(vals_list):
                if not vals.get('name'):
                    vals['name'] = str(index)
        records = super().create(vals_list)
        wizard = wizard if wizard and wizard.exists() else None
        if not wizard and records:
            try:
                wizard = records[0]._get_payment_register_wizard()
            except Exception:
                pass
        if wizard and hasattr(wizard, 'withholding_line_ids'):
            all_lines = wizard.withholding_line_ids.sorted(key=lambda l: (l.id or 0))
            for idx, line in enumerate(all_lines):
                if line.name != str(idx):
                    line.name = str(idx)
        return records

    def unlink(self):
        """ Override unlink to renumber remaining lines to 0, 1, 2... after deletion """
        payment_register = None
        line_ids_to_exclude = []
        for line in self:
            try:
                payment_register = line._get_payment_register_wizard()
                if line.id:
                    line_ids_to_exclude.append(line.id)
                break
            except Exception:
                pass
        result = super().unlink()
        if payment_register and hasattr(payment_register, 'withholding_line_ids'):
            lines = payment_register.withholding_line_ids.filtered(
                lambda l: l.id not in line_ids_to_exclude
            ).sorted('id')
            for index, line in enumerate(lines, start=0):
                if not line.name or line.name != str(index):
                    line.name = str(index)
        return result

    def _renumber_all_lines(self):
        """ Renumber all lines in the payment register to 0, 1, 2... """
        try:
            payment_register = self._get_payment_register_wizard()
        except Exception:
            payment_register = False
        if payment_register and hasattr(payment_register, 'withholding_line_ids'):
            all_lines = payment_register.withholding_line_ids
            saved_lines = [l for l in all_lines if l.id and isinstance(l.id, int)]
            new_lines = [l for l in all_lines if not l.id or not isinstance(l.id, int)]
            saved_lines_sorted = sorted(saved_lines, key=lambda x: x.id) if saved_lines else []
            for index, line in enumerate(saved_lines_sorted, start=0):
                expected_number = str(index)
                if not line.name or line.name != expected_number:
                    line.name = expected_number
            start_number = len(saved_lines_sorted)
            for index, line in enumerate(new_lines, start=start_number):
                expected_number = str(index)
                if not line.name or line.name != expected_number:
                    line.name = expected_number

    @api.depends('company_id', 'tax_id')
    def _compute_account_id(self):
        """Always assign Account from the tax's tax-repartition account."""
        for line in self:
            account = line._auto_account_from_tax(line.tax_id)
            if not account:
                account = line.company_id.withholding_tax_base_account_id
            line.account_id = account or line.account_id or False

    @api.depends('original_base_amount', 'comodel_percentage_paid_factor')
    def _compute_base_amount(self):
        """ Override to get base_amount from payment register wizard amount """
        # First call super to get the default computation
        super()._compute_base_amount()

        for line in self:
            # Only set base_amount if it's empty or zero (allows manual changes)
            if line.base_amount and line.base_amount > 0:
                continue  # Skip if already set (user has manually changed it)

            # Get the payment register wizard
            payment_register = line._get_payment_register_wizard()

            if payment_register:
                # Get amount from payment register wizard
                register_amount = 0.0

                # Check common amount fields in payment register
                if hasattr(payment_register, 'amount') and payment_register.amount:
                    register_amount = payment_register.amount
                elif hasattr(payment_register, 'payment_amount') and payment_register.payment_amount:
                    register_amount = payment_register.payment_amount
                elif hasattr(payment_register, 'source_amount') and payment_register.source_amount:
                    register_amount = payment_register.source_amount
                elif hasattr(payment_register, 'source_amount_currency') and payment_register.source_amount_currency:
                    register_amount = payment_register.source_amount_currency

                if register_amount and register_amount > 0:
                    # Get currency from payment register if available
                    register_currency = None
                    if hasattr(payment_register, 'currency_id') and payment_register.currency_id:
                        register_currency = payment_register.currency_id
                    elif hasattr(payment_register, 'source_currency_id') and payment_register.source_currency_id:
                        register_currency = payment_register.source_currency_id
                    elif hasattr(payment_register, 'company_id') and payment_register.company_id:
                        register_currency = payment_register.company_id.currency_id

                    # Convert currency if needed
                    if register_currency and line.comodel_currency_id:
                        if register_currency != line.comodel_currency_id:
                            rate = self.env['res.currency']._get_conversion_rate(
                                from_currency=register_currency,
                                to_currency=line.comodel_currency_id,
                                company=line.company_id,
                                date=line.comodel_date or fields.Date.today(),
                            )
                            register_amount = register_amount * rate

                    # Set base_amount from payment register wizard amount
                    # Only set if empty/zero (allows manual changes)
                    if line.comodel_currency_id:
                        line.base_amount = line.comodel_currency_id.round(register_amount)

    def _get_payment_register_wizard(self):
        """ Helper method to get the payment register wizard record (parent) """
        self.ensure_one()

        # Method 1: Try common parent field names in transient models
        # Check for wizard_id, payment_register_id, or parent_id
        for field_name in ['wizard_id', 'payment_register_id', 'parent_id', 'register_id']:
            if hasattr(self, field_name):
                parent = getattr(self, field_name, False)
                if parent and parent._name == 'account.payment.register':
                    return parent

        # Method 2: Try to get from active_id in context (most common when adding lines from form)
        if 'active_id' in self.env.context and 'active_model' in self.env.context:
            active_model = self.env.context.get('active_model')
            active_id = self.env.context.get('active_id')
            if active_model == 'account.payment.register' and active_id:
                return self.env['account.payment.register'].browse(active_id)

        # Method 3: Try to get from default_parent_id or default_wizard_id in context
        for default_field in ['default_parent_id', 'default_wizard_id', 'default_payment_register_id']:
            if default_field in self.env.context:
                parent_id = self.env.context.get(default_field)
                if parent_id:
                    return self.env['account.payment.register'].browse(parent_id)

        # Method 4: Search for payment register records that contain this line
        # This works if the line is already saved and linked
        if self.id:
            payment_register = self.env['account.payment.register'].search([
                ('withholding_line_ids', 'in', self.ids)
            ], limit=1)
            if payment_register:
                return payment_register

        # Method 5: Try to get from the recordset if we're in a recordset context
        # Sometimes the parent is accessible through the recordset
        if self._origin and hasattr(self._origin, '_get_comodel_partner'):
            # Try to find parent through the recordset
            pass

        return False

    @api.onchange('tax_id', 'base_amount', 'account_id')
    def _onchange_tax_id_set_number(self):
        """ Onchange: set sequence from position in wizard (fallback when create not yet run) and account from tax """
        try:
            wizard = self._get_payment_register_wizard()
            if wizard and hasattr(wizard, 'withholding_line_ids'):
                all_lines = wizard.withholding_line_ids.sorted(key=lambda l: (l.id or 0))
                for idx, line in enumerate(all_lines):
                    if line.id == self.id or line == self:
                        self.name = str(idx)
                        break
                else:
                    self.name = self._next_sequence_for_register(wizard)
            elif not self.name:
                self.name = '0'
        except Exception:
            if not self.name:
                self.name = '0'

        account = self._auto_account_from_tax(self.tax_id)
        if not account:
            account = self.company_id.withholding_tax_base_account_id
        if account:
            self.account_id = account

    @api.onchange('tax_id')
    def _onchange_tax_id_set_base_amount(self):
        """ Onchange when tax is selected - set base_amount ONLY if not already set """
        # Only set base_amount if it's empty or zero, and tax is selected
        if self.tax_id and (not self.base_amount or self.base_amount == 0):
            payment_register = self._get_payment_register_wizard()

            if payment_register:
                register_amount = 0.0
                if hasattr(payment_register, 'amount') and payment_register.amount:
                    register_amount = payment_register.amount
                elif hasattr(payment_register, 'payment_amount') and payment_register.payment_amount:
                    register_amount = payment_register.payment_amount
                elif hasattr(payment_register, 'source_amount') and payment_register.source_amount:
                    register_amount = payment_register.source_amount
                elif hasattr(payment_register, 'source_amount_currency') and payment_register.source_amount_currency:
                    register_amount = payment_register.source_amount_currency

                if register_amount and register_amount > 0:
                    # Get currency
                    register_currency = None
                    if hasattr(payment_register, 'currency_id') and payment_register.currency_id:
                        register_currency = payment_register.currency_id
                    elif hasattr(payment_register, 'source_currency_id') and payment_register.source_currency_id:
                        register_currency = payment_register.source_currency_id
                    elif hasattr(payment_register, 'company_id') and payment_register.company_id:
                        register_currency = payment_register.company_id.currency_id

                    # Convert currency if needed
                    if register_currency and self.comodel_currency_id:
                        if register_currency != self.comodel_currency_id:
                            rate = self.env['res.currency']._get_conversion_rate(
                                from_currency=register_currency,
                                to_currency=self.comodel_currency_id,
                                company=self.company_id,
                                date=self.comodel_date or fields.Date.today(),
                            )
                            register_amount = register_amount * rate

                    # Set base_amount from payment register wizard amount
                    # Only set if it's empty or zero (allows manual changes)
                    if self.comodel_currency_id:
                        self.base_amount = self.comodel_currency_id.round(register_amount)


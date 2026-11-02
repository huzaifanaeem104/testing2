# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.addons.base.models.res_bank import sanitize_account_number
from odoo.exceptions import UserError, RedirectWarning

STATEMENT_LINE_IMPORT_KEYS = {
    'date', 'payment_ref', 'ref', 'amount', 'unique_import_id',
    'account_number', 'partner_id', 'partner_name', 'journal_id',
    'sequence', 'transaction_type', 'foreign_currency_id',
    'amount_currency', 'narration', 'raw_data',
}


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_import_formats(self):
        return []

    def __get_bank_statements_available_sources(self):
        sources = super().__get_bank_statements_available_sources()
        formats = self._get_bank_statements_available_import_formats()
        if formats:
            formats = sorted(formats)
            sources.append((
                'file_import',
                _('Manual (or import %s)', ', '.join(formats)),
            ))
        return sources

    def create_document_from_attachment(self, attachment_ids=None):
        journal = self or self.browse(self.env.context.get('default_journal_id'))
        if journal.type in ('bank', 'cash', 'credit'):
            attachments = self.env['ir.attachment'].browse(attachment_ids)
            if not attachments:
                raise UserError(_('No attachment was provided'))
            return journal._import_bank_statement(attachments)
        return super().create_document_from_attachment(attachment_ids)

    def _import_bank_statement(self, attachments):
        if any(not attachment.raw for attachment in attachments):
            raise UserError(_('You uploaded an invalid or empty file.'))

        statement_ids = []
        errors = {}
        for attachment in attachments:
            try:
                currency_code, account_number, stmts_vals = self._parse_bank_statement_file(attachment)
                self._check_parsed_data(stmts_vals, account_number)
                journal = self._find_additional_data(currency_code, account_number)
                if not journal.default_account_id:
                    raise UserError(_(
                        'You have to set a Default Account for the journal: %s',
                        journal.name,
                    ))
                stmts_vals = self._complete_bank_statement_vals(
                    stmts_vals, journal, account_number, attachment,
                )
                created_ids, _lines, _notes = journal._create_bank_statements(stmts_vals)
                statement_ids.extend(created_ids)
                if journal.bank_statements_source != 'file_import':
                    journal.sudo().bank_statements_source = 'file_import'
            except (UserError, RedirectWarning) as error:
                errors[attachment.name] = error.args[0]

        statements = self.env['account.bank.statement'].browse(statement_ids)
        action = self.env['ir.actions.act_window']._for_xml_id(
            'account_statement_base.account_bank_statement_line_action'
        )
        action.update({
            'name': _('Imported Bank Statements'),
            'domain': [('statement_id', 'in', statements.ids)],
            'context': {
                'search_default_not_reconciled': 1,
                'default_journal_id': statements[:1].journal_id.id,
            },
        })
        if errors:
            error_msg = _('The following files could not be imported:\n')
            error_msg += '\n'.join(
                f'- {name}: {message}' for name, message in errors.items()
            )
            if statements:
                self.env.cr.commit()
                raise RedirectWarning(error_msg, action, _('View successfully imported statements'))
            raise UserError(error_msg)
        return action

    def _parse_bank_statement_file(self, attachment):
        raise RedirectWarning(
            message=_(
                'Could not make sense of the given file.\n'
                'Did you install the module to support this type of file?'
            ),
            action=self.env.ref('base.open_module_tree').id,
            button_text=_('Go to Apps'),
            additional_context={
                'search_default_name': 'account_bank_statement_import',
            },
        )

    def _check_parsed_data(self, stmts_vals, account_number):
        if not stmts_vals:
            raise UserError(_(
                "This file doesn't contain any statement for account %s.",
                account_number or '',
            ))
        if not any(vals.get('transactions') for vals in stmts_vals):
            raise UserError(_(
                "This file doesn't contain any transaction for account %s.",
                account_number or '',
            ))

    def _statement_import_check_bank_account(self, account_number):
        sanitized = (self.bank_account_id.sanitized_acc_number or '').split(' ')[0]
        return sanitized == account_number

    def _find_additional_data(self, currency_code, account_number):
        company_currency = self.env.company.currency_id
        currency = None
        sanitized_account_number = sanitize_account_number(account_number) if account_number else False

        if currency_code:
            currency = self.env['res.currency'].search(
                [('name', '=ilike', currency_code)], limit=1,
            )
            if not currency:
                raise UserError(_("No currency found matching '%s'.", currency_code))
            if currency == company_currency:
                currency = False

        journal = self
        if account_number:
            if journal and not journal.bank_account_id:
                journal.set_bank_account(account_number)
            elif not journal:
                journal = self.search([
                    ('bank_account_id.sanitized_acc_number', '=', sanitized_account_number),
                ], limit=1)
            elif not self._statement_import_check_bank_account(sanitized_account_number):
                raise UserError(_(
                    'The account of this statement (%(account)s) is not the same as the journal (%(journal)s).',
                    account=account_number,
                    journal=journal.bank_account_id.acc_number,
                ))

        if journal:
            journal_currency = journal.currency_id or journal.company_id.currency_id
            if currency is None:
                currency = journal_currency
            if currency and currency != journal_currency:
                raise UserError(_(
                    'The currency of the bank statement (%(code)s) is not the same as the currency of the journal (%(journal)s).',
                    code=currency.name,
                    journal=journal_currency.name,
                ))
        if not journal:
            raise UserError(_('Cannot find in which journal import this statement. Please manually select a journal.'))
        return journal

    def _complete_bank_statement_vals(self, stmts_vals, journal, account_number, attachment):
        for st_vals in stmts_vals:
            st_vals.setdefault('reference', attachment.name)
            cleaned = []
            for line_vals in st_vals.get('transactions') or []:
                line_vals['journal_id'] = journal.id
                if not line_vals.get('payment_ref'):
                    line_vals['payment_ref'] = line_vals.get('ref') or attachment.name
                journal._statement_line_import_update_unique_import_id(
                    line_vals, account_number or '',
                )
                cleaned.append({
                    key: value
                    for key, value in line_vals.items()
                    if key in STATEMENT_LINE_IMPORT_KEYS
                })
            st_vals['transactions'] = cleaned
        return stmts_vals

    def _create_bank_statements(self, stmts_vals, raise_no_imported_file=True):
        BankStatement = self.env['account.bank.statement']
        BankStatementLine = self.env['account.bank.statement.line']
        statement_ids = []
        statement_line_ids = []
        ignored = 0
        for st_vals in stmts_vals:
            filtered = []
            for line_vals in st_vals.get('transactions') or []:
                unique_id = line_vals.get('unique_import_id')
                already = unique_id and BankStatementLine.sudo().search(
                    [('unique_import_id', '=', unique_id)], limit=1,
                )
                if line_vals.get('amount') and not already:
                    filtered.append(line_vals)
                else:
                    ignored += 1
                    if st_vals.get('balance_start') is not None:
                        st_vals['balance_start'] += float(line_vals.get('amount') or 0.0)
            if not filtered:
                continue
            st_vals = dict(st_vals)
            st_vals.pop('transactions', None)
            st_vals['line_ids'] = [(0, 0, line) for line in filtered]
            statement = BankStatement.with_context(default_journal_id=self.id).create(st_vals)
            if not statement.name:
                statement.name = st_vals.get('reference')
            statement_ids.append(statement.id)
            statement_line_ids.extend(statement.line_ids.ids)
        if not statement_line_ids and raise_no_imported_file:
            raise UserError(_('You already have imported that file.'))
        notifications = []
        if ignored:
            notifications.append({
                'type': 'warning',
                'message': _(
                    '%d transactions had already been imported and were ignored.',
                    ignored,
                ),
            })
        return statement_ids, statement_line_ids, notifications

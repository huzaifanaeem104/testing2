# -*- coding: utf-8 -*-

import io

from lxml import etree

from odoo import models, _
from odoo.addons.base.models.res_bank import sanitize_account_number
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_import_formats(self):
        formats = super()._get_bank_statements_available_import_formats()
        formats.append('CAMT')
        return formats

    def _camt_root(self, attachment):
        try:
            root = etree.parse(io.BytesIO(attachment.raw)).getroot()
        except etree.XMLSyntaxError:
            return None
        tag = etree.QName(root).localname.lower()
        raw_tag = (root.tag or '').lower()
        if 'camt.053' in raw_tag or tag in ('document', 'bktocstmrstmt'):
            return root
        return None

    def _camt_find(self, node, localname):
        if node is None:
            return None
        matches = node.xpath(f'.//*[local-name()="{localname}"]')
        return matches[0] if matches else None

    def _camt_text(self, node, localname, default=''):
        found = self._camt_find(node, localname)
        if found is None or found.text is None:
            return default
        return found.text.strip()

    def _camt_signed_amount(self, amount_node, indicator_node, default_indicator=''):
        if amount_node is None or not amount_node.text:
            return 0.0
        amount = float(amount_node.text.replace(',', '.'))
        indicator = (indicator_node.text if indicator_node is not None and indicator_node.text else default_indicator)
        if (indicator or '').upper() == 'DBIT':
            return -abs(amount)
        return amount

    def _camt_account_number(self, statement):
        acct = self._camt_find(statement, 'Acct')
        if acct is None:
            return ''
        iban_nodes = acct.xpath('.//*[local-name()="IBAN"]')
        if iban_nodes and iban_nodes[0].text:
            return sanitize_account_number(iban_nodes[0].text)
        other_nodes = acct.xpath('.//*[local-name()="Othr"]/*[local-name()="Id"]')
        if other_nodes and other_nodes[0].text:
            return sanitize_account_number(other_nodes[0].text)
        return ''

    def _camt_balance(self, statement, codes):
        for balance in statement.xpath('.//*[local-name()="Bal"]'):
            code = self._camt_text(balance, 'Cd')
            if code in codes:
                return self._camt_signed_amount(
                    self._camt_find(balance, 'Amt'),
                    self._camt_find(balance, 'CdtDbtInd'),
                )
        return None

    def _parse_bank_statement_file(self, attachment):
        root = self._camt_root(attachment)
        if root is None:
            return super()._parse_bank_statement_file(attachment)
        return self._parse_camt_root(root, attachment)

    def _parse_camt_root(self, root, attachment):
        statements_by_account = {}
        currency_by_account = {}
        journal_account = sanitize_account_number(self.bank_acc_number or '')
        journal_currency = self.currency_id or self.company_id.currency_id

        for statement in root.xpath('.//*[local-name()="Stmt"]'):
            account = self._camt_account_number(statement)
            currency = self._camt_text(statement, 'Ccy')
            if not currency:
                amount_node = self._camt_find(statement, 'Amt')
                currency = amount_node.get('Ccy') if amount_node is not None else ''
            if currency and journal_currency and currency != journal_currency.name:
                continue

            statement_name = self._camt_text(statement, 'LglSeqNb') or self._camt_text(statement, 'Id') or attachment.name
            transactions = []
            for index, entry in enumerate(statement.xpath('.//*[local-name()="Ntry"]'), start=1):
                details = entry.xpath('.//*[local-name()="TxDtls"]') or [entry]
                for detail in details:
                    amount = self._camt_signed_amount(
                        self._camt_find(detail, 'Amt') or self._camt_find(entry, 'Amt'),
                        self._camt_find(detail, 'CdtDbtInd') or self._camt_find(entry, 'CdtDbtInd'),
                    )
                    if not amount:
                        continue
                    date_text = (
                        self._camt_text(entry, 'Dt')
                        or self._camt_text(entry, 'DtTm')[:10]
                    )
                    label = (
                        self._camt_text(detail, 'Ustrd')
                        or self._camt_text(detail, 'AddtlNtryInf')
                        or self._camt_text(entry, 'AddtlNtryInf')
                        or statement_name
                    )
                    partner_name = self._camt_text(detail, 'Nm')
                    account_number = sanitize_account_number(
                        self._camt_text(detail, 'IBAN') or ''
                    ) or False
                    ref = (
                        self._camt_text(detail, 'AcctSvcrRef')
                        or self._camt_text(entry, 'NtryRef')
                        or self._camt_text(detail, 'EndToEndId')
                    )
                    transactions.append({
                        'date': date_text or False,
                        'payment_ref': label,
                        'ref': ref or False,
                        'amount': amount,
                        'partner_name': partner_name or False,
                        'account_number': account_number,
                        'unique_import_id': ref or f'{statement_name}-{index}-{amount}-{label}',
                        'sequence': len(transactions) + 1,
                    })

            if not transactions:
                continue
            vals = {
                'name': statement_name,
                'reference': attachment.name,
                'transactions': transactions,
            }
            start = self._camt_balance(statement, {'OPBD', 'PRCD', 'ITBD'})
            end = self._camt_balance(statement, {'CLBD', 'CLAV'})
            if start is not None:
                vals['balance_start'] = start
            if end is not None:
                vals['balance_end_real'] = end
            statements_by_account.setdefault(account, []).append(vals)
            currency_by_account[account] = currency or None

        if not statements_by_account:
            raise UserError(_('No CAMT.053 transactions matching this journal were found.'))

        if len(statements_by_account) > 1:
            if not journal_account:
                raise UserError(_(
                    'This CAMT file contains several accounts. Set the IBAN on the journal first.'
                ))
            statements = statements_by_account.get(journal_account)
            if not statements:
                raise UserError(_(
                    'This CAMT file does not contain the journal account %s.',
                    self.bank_acc_number,
                ))
            return currency_by_account.get(journal_account), journal_account, statements

        account_number = next(iter(statements_by_account))
        return (
            currency_by_account.get(account_number),
            account_number or None,
            statements_by_account[account_number],
        )

# -*- coding: utf-8 -*-

import re
from datetime import datetime

from odoo import models, _
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_import_formats(self):
        formats = super()._get_bank_statements_available_import_formats()
        formats.append('OFX')
        return formats

    def _is_ofx_statement(self, attachment):
        raw = attachment.raw or b''
        if raw.startswith(b'OFXHEADER'):
            return True
        return b'<ofx>' in raw.lower()

    def _parse_bank_statement_file(self, attachment):
        if not self._is_ofx_statement(attachment):
            return super()._parse_bank_statement_file(attachment)
        return self._parse_ofx_attachment(attachment)

    def _ofx_tag(self, text, name):
        match = re.search(rf'<{name}>([^<\r\n]+)', text, re.IGNORECASE)
        return match.group(1).strip() if match else ''

    def _parse_ofx_date(self, value):
        digits = re.sub(r'[^0-9]', '', value or '')
        if len(digits) >= 8:
            return datetime.strptime(digits[:8], '%Y%m%d').date()
        return False

    def _parse_ofx_amount(self, value):
        text = (value or '0').replace(' ', '').replace(',', '.')
        return float(text)

    def _parse_ofx_attachment(self, attachment):
        text = (attachment.raw or b'').decode('utf-8', errors='replace')
        account_number = self._ofx_tag(text, 'ACCTID') or None
        currency = self._ofx_tag(text, 'CURDEF') or None
        balance = self._ofx_tag(text, 'BALAMT')
        transactions = []
        total = 0.0

        blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, re.IGNORECASE | re.DOTALL)
        if not blocks:
            # OFX 1.x sometimes omits the closing tag; split on the opening tag.
            parts = re.split(r'<STMTTRN>', text, flags=re.IGNORECASE)[1:]
            blocks = []
            for part in parts:
                end = re.search(r'</STMTTRN>|<STMTTRN>|<LEDGERBAL>|<BANKTRANLIST>', part, re.IGNORECASE)
                blocks.append(part[:end.start()] if end else part)

        for index, block in enumerate(blocks, start=1):
            amount = self._parse_ofx_amount(self._ofx_tag(block, 'TRNAMT'))
            if not amount:
                continue
            payee = self._ofx_tag(block, 'NAME')
            memo = self._ofx_tag(block, 'MEMO')
            fitid = self._ofx_tag(block, 'FITID')
            check = self._ofx_tag(block, 'CHECKNUM')
            label = ': '.join(part for part in (payee, memo) if part) or check or fitid or attachment.name
            total += amount
            transactions.append({
                'date': self._parse_ofx_date(self._ofx_tag(block, 'DTPOSTED')),
                'payment_ref': label,
                'ref': check or fitid or False,
                'amount': amount,
                'partner_name': payee or False,
                'unique_import_id': fitid or f'{attachment.name}-{index}-{amount}-{label}',
                'sequence': len(transactions) + 1,
            })

        if not transactions:
            raise UserError(_('No OFX transactions were found in this file.'))

        statement = {
            'reference': attachment.name,
            'transactions': transactions,
        }
        if balance:
            end_balance = self._parse_ofx_amount(balance)
            statement['balance_end_real'] = end_balance
            statement['balance_start'] = end_balance - total
        return currency, account_number, [statement]

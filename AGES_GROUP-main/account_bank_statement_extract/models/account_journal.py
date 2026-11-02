# -*- coding: utf-8 -*-

import re

from odoo import models, _
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _name = 'account.journal'
    _inherit = ['account.journal', 'account.extract.mixin']

    def _get_bank_statements_available_import_formats(self):
        formats = super()._get_bank_statements_available_import_formats()
        if self.env.company.extract_bank_statement_digitalization_mode != 'no_send':
            formats.extend(['PDF', 'JPEG', 'PNG'])
        return formats

    def _parse_bank_statement_file(self, attachment):
        if not self._extract_is_ocrizable(attachment):
            return super()._parse_bank_statement_file(attachment)
        if self.company_id.extract_bank_statement_digitalization_mode == 'no_send':
            return super()._parse_bank_statement_file(attachment)
        return self._parse_ocr_bank_statement(attachment)

    def _parse_ocr_bank_statement(self, attachment):
        text = self._extract_attachment_text(attachment)
        transactions = []
        for index, raw_line in enumerate((text or '').splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            amounts = self._extract_amounts(line)
            dates = self._extract_dates(line)
            if not amounts or not dates:
                continue
            amount = amounts[-1]
            if not amount:
                continue
            label = DATE_LINE_RE.sub('', line)
            label = AMOUNT_LINE_RE.sub('', label).strip(' -|\t') or attachment.name
            transactions.append({
                'date': dates[0],
                'payment_ref': label[:128],
                'amount': amount,
                'unique_import_id': f'{attachment.name}-{index}-{dates[0]}-{amount}-{label}',
                'sequence': len(transactions) + 1,
            })
        if not transactions:
            raise UserError(_(
                'No bank transactions could be read from %s. '
                'The scan needs a date and an amount on each line.',
                attachment.name,
            ))
        return None, None, [{
            'reference': attachment.name,
            'transactions': transactions,
        }]


DATE_LINE_RE = re.compile(r'\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}')
AMOUNT_LINE_RE = re.compile(r'(?:(?:PKR|USD|EUR|GBP|Rs\.?|₨)\s*)?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})|-?\d+\.\d{2}')

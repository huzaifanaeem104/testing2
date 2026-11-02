# -*- coding: utf-8 -*-

import csv
import io
from datetime import datetime

from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools.misc import ustr

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

DATE_HEADERS = {'date', 'transaction date', 'value date', 'booking date', 'posted'}
LABEL_HEADERS = {
    'description', 'label', 'payment_ref', 'memo', 'narration',
    'particulars', 'details', 'name', 'payee',
}
AMOUNT_HEADERS = {'amount', 'transaction amount', 'value'}
DEBIT_HEADERS = {'debit', 'withdrawal', 'money out', 'paid out'}
CREDIT_HEADERS = {'credit', 'deposit', 'money in', 'paid in'}
REF_HEADERS = {'ref', 'reference', 'cheque', 'check', 'fitid', 'id'}
PARTNER_HEADERS = {'partner', 'partner_name', 'counterparty'}


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_import_formats(self):
        formats = super()._get_bank_statements_available_import_formats()
        formats.extend(['CSV', 'XLS', 'XLSX'])
        return formats

    def _is_spreadsheet_statement(self, attachment):
        name = (attachment.name or '').lower()
        return name.endswith(('.csv', '.xls', '.xlsx'))

    def _parse_bank_statement_file(self, attachment):
        if not self._is_spreadsheet_statement(attachment):
            return super()._parse_bank_statement_file(attachment)
        rows = self._read_statement_rows(attachment)
        if not rows:
            raise UserError(_('The file %s does not contain any rows.', attachment.name))
        return self._rows_to_statement_vals(rows, attachment.name)

    def _read_statement_rows(self, attachment):
        name = (attachment.name or '').lower()
        if name.endswith('.csv'):
            return self._read_csv_rows(attachment.raw)
        if name.endswith('.xlsx'):
            return self._read_xlsx_rows(attachment.raw)
        if name.endswith('.xls'):
            raise UserError(_(
                'XLS import needs the file saved as XLSX or CSV. '
                'Please re-export the statement and try again.'
            ))
        return []

    def _read_csv_rows(self, raw):
        text = raw.decode('utf-8-sig', errors='replace')
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        return [[ustr(cell).strip() for cell in row] for row in reader if any(row)]

    def _read_xlsx_rows(self, raw):
        if load_workbook is None:
            raise UserError(_('The Python library openpyxl is required to import XLSX files.'))
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = workbook.active
        rows = []
        for row in sheet.iter_rows(values_only=True):
            values = ['' if cell is None else ustr(cell).strip() for cell in row]
            if any(values):
                rows.append(values)
        return rows

    def _normalize_header(self, value):
        return (value or '').strip().lower().replace('_', ' ')

    def _map_columns(self, headers):
        mapping = {}
        for index, header in enumerate(headers):
            name = self._normalize_header(header)
            if name in DATE_HEADERS and 'date' not in mapping:
                mapping['date'] = index
            elif name in LABEL_HEADERS and 'payment_ref' not in mapping:
                mapping['payment_ref'] = index
            elif name in AMOUNT_HEADERS and 'amount' not in mapping:
                mapping['amount'] = index
            elif name in DEBIT_HEADERS and 'debit' not in mapping:
                mapping['debit'] = index
            elif name in CREDIT_HEADERS and 'credit' not in mapping:
                mapping['credit'] = index
            elif name in REF_HEADERS and 'ref' not in mapping:
                mapping['ref'] = index
            elif name in PARTNER_HEADERS and 'partner_name' not in mapping:
                mapping['partner_name'] = index
        if 'date' not in mapping:
            mapping['date'] = 0
        if 'payment_ref' not in mapping and len(headers) > 1:
            mapping['payment_ref'] = 1
        if 'amount' not in mapping and 'debit' not in mapping and len(headers) > 2:
            mapping['amount'] = 2
        return mapping

    def _parse_amount(self, value):
        if value in (None, ''):
            return 0.0
        text = ustr(value).strip().replace(' ', '').replace(',', '')
        if text.startswith('(') and text.endswith(')'):
            text = '-' + text[1:-1]
        try:
            return float(text)
        except ValueError:
            raise UserError(_('Could not parse amount "%s".', value))

    def _parse_date(self, value):
        if not value:
            raise UserError(_('A transaction is missing a date.'))
        if hasattr(value, 'date'):
            return value.date()
        if hasattr(value, 'year') and hasattr(value, 'month'):
            return value
        text = ustr(value).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
        raise UserError(_('Could not parse date "%s". Use YYYY-MM-DD.', value))

    def _rows_to_statement_vals(self, rows, filename):
        mapping = self._map_columns(rows[0])
        transactions = []
        for index, row in enumerate(rows[1:], start=2):
            if not any(row):
                continue
            def cell(key):
                col = mapping.get(key)
                return row[col] if col is not None and col < len(row) else ''

            if mapping.get('amount') is not None:
                amount = self._parse_amount(cell('amount'))
            else:
                amount = self._parse_amount(cell('credit')) - self._parse_amount(cell('debit'))
            if not amount:
                continue
            payment_ref = cell('payment_ref') or cell('ref') or filename
            date = self._parse_date(cell('date'))
            transactions.append({
                'date': date,
                'payment_ref': payment_ref,
                'ref': cell('ref') or False,
                'amount': amount,
                'partner_name': cell('partner_name') or False,
                'unique_import_id': f'{filename}-{index}-{date}-{amount}-{payment_ref}',
                'sequence': len(transactions) + 1,
            })
        if not transactions:
            raise UserError(_(
                'No transactions found. The first row must contain headers such as Date, Description and Amount.'
            ))
        return None, None, [{
            'reference': filename,
            'transactions': transactions,
        }]

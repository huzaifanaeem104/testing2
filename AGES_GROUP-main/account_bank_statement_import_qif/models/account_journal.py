# -*- coding: utf-8 -*-

import io

from dateutil import parser as date_parser

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    qif_decimal_point = fields.Char(
        string='QIF Decimal Separator',
        default='.',
        help='Decimal separator used in QIF amounts.',
    )
    qif_date_format = fields.Selection(
        selection=[
            ('month_first', 'mm/dd/yy'),
            ('day_first', 'dd/mm/yy'),
        ],
        default='day_first',
        string='QIF Dates format',
        help='Historic QIF uses month-first dates. Many banks outside the US use day-first.',
    )

    def _get_bank_statements_available_import_formats(self):
        formats = super()._get_bank_statements_available_import_formats()
        formats.append('QIF')
        return formats

    def _is_qif_statement(self, attachment):
        return (attachment.raw or b'').lstrip().startswith(b'!Type:')

    def _parse_bank_statement_file(self, attachment):
        if not self._is_qif_statement(attachment):
            return super()._parse_bank_statement_file(attachment)

        lines = [
            line.rstrip(b'\r\n')
            for line in io.BytesIO(attachment.raw.lstrip())
        ]
        try:
            header = lines[0].split(b':', 1)[1].strip()
        except (IndexError, AttributeError):
            raise UserError(_('Could not read the QIF file header.'))

        if header not in (b'Bank', b'Cash', b'CCard'):
            raise UserError(_(
                'This QIF file type (%s) is not a bank, cash or credit-card statement.',
                header.decode(errors='replace'),
            ))

        transactions = []
        current = {'labels': []}
        total = 0.0
        dayfirst = self.qif_date_format == 'day_first'
        decimal = self.qif_decimal_point or '.'

        for raw_line in lines[1:]:
            line = raw_line.strip()
            if not line:
                continue
            code = line[:1]
            data = line[1:]
            if code == b'D':
                current['date'] = date_parser.parse(
                    data.decode(errors='replace'),
                    fuzzy=True,
                    dayfirst=dayfirst,
                ).date()
            elif code == b'T':
                amount_text = data.decode(errors='replace')
                if decimal == ',':
                    amount_text = amount_text.replace('.', '').replace(',', '.')
                else:
                    amount_text = amount_text.replace(',', '')
                current['amount'] = float(amount_text)
                total += current['amount']
            elif code == b'N':
                current['ref'] = data.decode(errors='replace')
            elif code == b'P':
                current['labels'].append(data.decode(errors='replace'))
            elif code == b'M':
                current['labels'].append(data.decode(errors='replace'))
            elif code == b'^':
                labels = [label for label in current.get('labels') or [] if label]
                amount = current.get('amount')
                if amount:
                    transactions.append({
                        'date': current.get('date'),
                        'payment_ref': ': '.join(labels) or current.get('ref') or attachment.name,
                        'ref': current.get('ref'),
                        'amount': amount,
                        'unique_import_id': '-'.join(filter(None, [
                            attachment.name,
                            str(current.get('date') or ''),
                            str(amount),
                            current.get('ref') or (labels[0] if labels else ''),
                            str(len(transactions) + 1),
                        ])),
                        'sequence': len(transactions) + 1,
                    })
                current = {'labels': []}

        if not transactions:
            raise UserError(_('No QIF transactions were found in this file.'))
        return None, None, [{
            'reference': attachment.name,
            'balance_end_real': total,
            'transactions': transactions,
        }]

# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

AMOUNT_RE = re.compile(r'(?:(?:PKR|USD|EUR|GBP|Rs\.?|₨)\s*)?(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2}|\d+)')
DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})')


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    extract_state = fields.Selection(
        [
            ('no', 'Not digitized'),
            ('waiting', 'To digitize'),
            ('done', 'Digitized'),
            ('failed', 'Digitization failed'),
        ],
        default='no',
        copy=False,
    )
    extract_text = fields.Text(copy=False)

    def action_digitize_receipt(self):
        for expense in self:
            expense._digitize_from_attachments()
        return True

    def _digitize_from_attachments(self):
        self.ensure_one()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'hr.expense'),
            ('res_id', '=', self.id),
        ])
        if not attachments:
            raise UserError(_('Add a receipt attachment before digitizing this expense.'))
        text = self._extract_text_from_attachments(attachments)
        values = self._parse_receipt_text(text)
        values['extract_text'] = text
        values['extract_state'] = 'done' if values.get('total_amount_currency') or values.get('name') else 'failed'
        self.write(values)
        return values

    def _extract_text_from_attachments(self, attachments):
        chunks = []
        for attachment in attachments:
            name = attachment.name or ''
            chunks.append(name)
            raw = attachment.raw or b''
            if attachment.mimetype and attachment.mimetype.startswith('text/'):
                chunks.append(raw.decode('utf-8', errors='replace'))
                continue
            try:
                import pytesseract
                from PIL import Image
                import io
                if attachment.mimetype and attachment.mimetype.startswith('image/'):
                    image = Image.open(io.BytesIO(raw))
                    chunks.append(pytesseract.image_to_string(image))
            except Exception as error:
                _logger.info('OCR fallback used for %s: %s', name, error)
        return '\n'.join(chunk for chunk in chunks if chunk)

    def _parse_receipt_text(self, text):
        values = {}
        amounts = [float(match.replace(',', '')) for match in AMOUNT_RE.findall(text or '')]
        if amounts:
            values['total_amount_currency'] = max(amounts)
        dates = DATE_RE.findall(text or '')
        if dates:
            raw_date = dates[0]
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d/%m/%y'):
                try:
                    values['date'] = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
        lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
        if lines and not self.name:
            values['name'] = lines[0][:128]
        return values

    @api.model_create_multi
    def create(self, vals_list):
        expenses = super().create(vals_list)
        if self.env.company.expense_extract_mode == 'auto':
            for expense in expenses:
                attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'hr.expense'),
                    ('res_id', '=', expense.id),
                ])
                if attachments:
                    try:
                        expense._digitize_from_attachments()
                    except UserError:
                        expense.extract_state = 'failed'
        return expenses

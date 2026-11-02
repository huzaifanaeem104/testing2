# -*- coding: utf-8 -*-

import io
import logging
import re
from datetime import datetime

from odoo import models
from odoo.tools.pdf import PdfReader

_logger = logging.getLogger(__name__)

AMOUNT_RE = re.compile(
    r'(?:(?:PKR|USD|EUR|GBP|Rs\.?|₨)\s*)?(-?\d{1,3}(?:,\d{3})*(?:\.\d{2})|-?\d+\.\d{2})'
)
DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})')
INVOICE_REF_RE = re.compile(
    r'(?:invoice|bill|tax invoice|inv|ref(?:erence)?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-\/]{2,})',
    re.IGNORECASE,
)
TAX_RE = re.compile(r'(?:gst|vat|sales tax|tax)\s*(?:@|at)?\s*(\d{1,2}(?:\.\d+)?)\s*%', re.IGNORECASE)


class AccountExtractMixin(models.AbstractModel):
    _name = 'account.extract.mixin'
    _description = 'Accounting document text extraction'

    def _extract_is_ocrizable(self, attachment):
        raw = attachment.raw or b''
        mimetype = (attachment.mimetype or '').lower()
        name = (attachment.name or '').lower()
        return (
            raw.strip().startswith(b'%PDF')
            or mimetype in ('application/pdf', 'image/png', 'image/jpeg', 'image/jpg')
            or name.endswith(('.pdf', '.png', '.jpg', '.jpeg'))
        )

    def _extract_attachment_text(self, attachments):
        chunks = []
        for attachment in attachments:
            chunks.append(attachment.name or '')
            raw = attachment.raw or b''
            mimetype = (attachment.mimetype or '').lower()
            if mimetype.startswith('text/'):
                chunks.append(raw.decode('utf-8', errors='replace'))
                continue
            if raw.strip().startswith(b'%PDF') or mimetype == 'application/pdf':
                chunks.append(self._extract_pdf_text(raw))
                continue
            if mimetype.startswith('image/'):
                chunks.append(self._extract_image_text(raw, attachment.name))
        return '\n'.join(chunk for chunk in chunks if chunk)

    def _extract_pdf_text(self, raw):
        try:
            reader = PdfReader(io.BytesIO(raw))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or '')
            return '\n'.join(pages)
        except Exception as error:
            _logger.info('PDF text extraction failed: %s', error)
            return ''

    def _extract_image_text(self, raw, name=''):
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(io.BytesIO(raw)))
        except Exception as error:
            _logger.info('Image OCR fallback used for %s: %s', name, error)
            return ''

    def _extract_parse_date(self, value):
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return False

    def _extract_amounts(self, text):
        amounts = []
        for match in AMOUNT_RE.findall(text or ''):
            try:
                amounts.append(float(match.replace(',', '')))
            except ValueError:
                continue
        return amounts

    def _extract_dates(self, text):
        dates = []
        for match in DATE_RE.findall(text or ''):
            parsed = self._extract_parse_date(match)
            if parsed:
                dates.append(parsed)
        return dates

    def _extract_invoice_ref(self, text):
        match = INVOICE_REF_RE.search(text or '')
        return match.group(1) if match else False

    def _extract_tax_percent(self, text):
        match = TAX_RE.search(text or '')
        return float(match.group(1)) if match else False

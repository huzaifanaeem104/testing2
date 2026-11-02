# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'account.extract.mixin']

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

    def _extract_mode(self):
        self.ensure_one()
        if self.is_purchase_document(include_receipts=True):
            return self.company_id.extract_in_invoice_digitalization_mode
        if self.is_sale_document(include_receipts=True):
            return self.company_id.extract_out_invoice_digitalization_mode
        return 'no_send'

    def _should_auto_digitize(self):    
        self.ensure_one()
        return (
            self.state == 'draft'
            and self._extract_mode() == 'auto_send'
            and self.extract_state != 'done'
        )

    def action_digitize_document(self):
        for move in self:
            move._digitize_from_attachments()
        return True

    def _get_digitize_attachments(self):
        self.ensure_one()
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id),
        ])

    def _digitize_from_attachments(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft documents can be digitized.'))
        attachments = self._get_digitize_attachments()
        if not attachments:
            raise UserError(_('Add a PDF or scanned attachment before digitizing.'))
        text = self._extract_attachment_text(attachments)
        values = self._parse_invoice_text(text)
        values['extract_text'] = text
        line_commands = values.pop('invoice_line_ids', False)
        values['extract_state'] = 'done' if values or line_commands else 'failed'
        if values:
            self.write(values)
        if line_commands and not self.invoice_line_ids:
            self.write({'invoice_line_ids': line_commands})
        return values

    def _parse_invoice_text(self, text):
        values = {}
        dates = self._extract_dates(text)
        if dates and not self.invoice_date:
            values['invoice_date'] = dates[0]
        ref = self._extract_invoice_ref(text)
        if ref and not self.ref:
            values['ref'] = ref
        partner = self._match_partner_from_text(text)
        if partner and not self.partner_id:
            values['partner_id'] = partner.id
        amounts = [abs(amount) for amount in self._extract_amounts(text) if amount]
        if amounts and not self.invoice_line_ids:
            total = max(amounts)
            tax_percent = self._extract_tax_percent(text)
            values['invoice_line_ids'] = self._prepare_extracted_lines(total, tax_percent, text)
        return values

    def _match_partner_from_text(self, text):
        partners = self.env['res.partner'].search([
            ('parent_id', '=', False),
            ('company_id', 'in', [False, self.company_id.id]),
        ], limit=200)
        haystack = (text or '').lower()
        for partner in partners:
            if partner.name and len(partner.name) > 3 and partner.name.lower() in haystack:
                return partner
        vat_match = re.search(r'\b([A-Z]{2,3}\d{5,}|\d{7,})\b', text or '')
        if vat_match:
            return self.env['res.partner'].search([
                ('vat', 'ilike', vat_match.group(1)),
                ('company_id', 'in', [False, self.company_id.id]),
            ], limit=1)
        return self.env['res.partner']

    def _prepare_extracted_lines(self, total, tax_percent, text):
        tax = self._find_tax(tax_percent)
        label = _('Digitized document')
        lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
        if lines:
            label = lines[0][:128]
        if self.company_id.extract_single_line_per_tax or not tax:
            return [(0, 0, {
                'name': label,
                'quantity': 1,
                'price_unit': total,
                'tax_ids': [(6, 0, tax.ids)] if tax else False,
            })]
        return [(0, 0, {
            'name': label,
            'quantity': 1,
            'price_unit': total,
            'tax_ids': [(6, 0, tax.ids)],
        })]

    def _find_tax(self, tax_percent):
        if not tax_percent:
            return self.env['account.tax']
        tax_type = 'purchase' if self.is_purchase_document(include_receipts=True) else 'sale'
        return self.env['account.tax'].search([
            ('type_tax_use', '=', tax_type),
            ('amount', '=', tax_percent),
            ('company_id', '=', self.company_id.id),
            ('amount_type', '=', 'percent'),
        ], limit=1)

    def _extend_with_attachments(self, attachments, new=False):
        res = super()._extend_with_attachments(attachments, new=new)
        moves = self
        linked = attachments.filtered(lambda att: att.res_model == 'account.move' and att.res_id)
        if linked:
            moves |= self.browse(linked.mapped('res_id'))
        for move in moves:
            if move._should_auto_digitize():
                try:
                    move._digitize_from_attachments()
                except UserError:
                    move.extract_state = 'failed'
        return res

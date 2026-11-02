# -*- coding: utf-8 -*-

from odoo import api, models

from .common import (
    accounting_lines,
    first_project,
    move_line_rows,
    report_base_values,
    selection_label,
)


class ReportJournalEntry(models.AbstractModel):
    _name = 'report.ages_reports.journal_entry'
    _description = 'Journal Entry Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        moves = self.env['account.move'].browse(docids)
        docs = []
        for move in moves:
            project = first_project(move)
            docs.append({
                'record': move,
                'lines': move_line_rows(self.env, move.line_ids),
                'project_name': project.display_name if project else '',
                'state_label': selection_label(move, 'state'),
                'total_debit': sum(move.line_ids.mapped('debit')),
                'total_credit': sum(move.line_ids.mapped('credit')),
            })
        values = report_base_values(
            self.env, docids, 'account.move', moves,
            'Journal Entry',
            'Print JEs · Landscape',
        )
        values['entries'] = docs
        return values


class ReportVendorBill(models.AbstractModel):
    _name = 'report.ages_reports.vendor_bill'
    _description = 'Vendor Bill Print'

    def _bill_line_rows(self, move):
        rows = []
        lines = move.invoice_line_ids.filtered(
            lambda line: line.display_type not in ('line_section', 'line_note')
        )
        for line in lines:
            rows.append({
                'product': line.product_id.display_name or '',
                'name': line.name or '',
                'account': line.account_id.display_name or '',
                'qty': line.quantity,
                'uom': line.product_uom_id.display_name if line.product_uom_id else '',
                'price': line.price_unit,
                'taxes': ', '.join(line.tax_ids.mapped('name')),
                'subtotal': line.price_subtotal,
            })
        return rows

    def _bill_source(self, move):
        if 'purchase_line_id' in move.invoice_line_ids._fields:
            orders = move.invoice_line_ids.mapped('purchase_line_id.order_id')
            if orders:
                return ', '.join(orders.mapped('name'))
        return move.invoice_origin or ''

    @api.model
    def _get_report_values(self, docids, data=None):
        moves = self.env['account.move'].browse(docids).filtered(
            lambda move: move.is_purchase_document(include_receipts=True)
        )
        docs = []
        for move in moves:
            project = first_project(move)
            title = 'Vendor Credit Note' if move.move_type == 'in_refund' else 'Vendor Bill'
            docs.append({
                'record': move,
                'title': title,
                'lines': self._bill_line_rows(move),
                'vendor_name': move.partner_id.display_name or '',
                'project_name': (
                    project.display_name
                    or move.ages_project_id.display_name
                    or ''
                ),
                'contract_description': move.ages_contract_description or '',
                'contract_name': move.ages_contract_id.display_name or '',
                'source': self._bill_source(move),
                'state_label': selection_label(move, 'state'),
                'bill_type_label': selection_label(move, 'ages_bill_type'),
                'currency': move.currency_id or move.company_id.currency_id or self.env.company.currency_id,
            })
        values = report_base_values(
            self.env, docids, 'account.move', moves,
            'Vendor Bill',
            'Print Bill · A4 Portrait',
        )
        values['entries'] = docs
        return values


class ReportJournalItem(models.AbstractModel):
    _name = 'report.ages_reports.journal_item'
    _description = 'Journal Items Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        lines = accounting_lines(self.env['account.move.line'].browse(docids))
        groups = []
        for move in lines.mapped('move_id'):
            move_lines = lines.filtered(lambda line: line.move_id == move)
            groups.append({
                'move': move,
                'lines': move_line_rows(self.env, move_lines),
                'total_debit': sum(move_lines.mapped('debit')),
                'total_credit': sum(move_lines.mapped('credit')),
            })
        values = report_base_values(
            self.env, docids, 'account.move.line', lines.mapped('move_id'),
            'Journal Items',
            'Print Journal Items · Landscape',
        )
        values['groups'] = groups
        values['grand_debit'] = sum(lines.mapped('debit'))
        values['grand_credit'] = sum(lines.mapped('credit'))
        return values


class ReportExpense(models.AbstractModel):
    _name = 'report.ages_reports.expense'
    _description = 'Expense Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        expenses = self.env['ages.expense'].browse(docids)
        docs = []
        for expense in expenses:
            rows = []
            for line in expense.line_ids:
                rows.append({
                    'account': line.account_id.display_name or '',
                    'partner': line.partner_id.display_name or '',
                    'project': line.project_id.display_name or '',
                    'name': line.name or '',
                    'amount': line.amount,
                })
            project = first_project(expense)
            docs.append({
                'record': expense,
                'lines': rows,
                'project_name': project.display_name if project else '',
                'state_label': selection_label(expense, 'state'),
                'currency': expense.currency_id or expense.company_id.currency_id or self.env.company.currency_id,
            })
        values = report_base_values(
            self.env, docids, 'ages.expense', expenses,
            'Expense',
            'Print Expense · Landscape',
        )
        values['entries'] = docs
        return values


class ReportPayment(models.AbstractModel):
    _name = 'report.ages_reports.payment'
    _description = 'Payment Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        payments = self.env['account.payment'].browse(docids)
        docs = []
        for payment in payments:
            project = first_project(payment)
            detail_rows = []
            if 'payment_detail_line_ids' in payment._fields:
                for line in payment.payment_detail_line_ids:
                    detail_rows.append({
                        'journal': line.destination_journal_id.display_name or '',
                        'vendor': line.partner_id.display_name if 'partner_id' in line._fields else '',
                        'project': line.ages_project_id.display_name or '',
                        'description': line.description or '',
                        'amount': line.amount,
                    })
            move_lines = payment.move_id.line_ids if payment.move_id else payment.env['account.move.line']
            docs.append({
                'record': payment,
                'project_name': project.display_name if project else '',
                'state_label': selection_label(payment, 'state'),
                'payment_type_label': selection_label(payment, 'payment_type'),
                'details': detail_rows,
                'lines': move_line_rows(self.env, move_lines),
                'total_debit': sum(move_lines.mapped('debit')),
                'total_credit': sum(move_lines.mapped('credit')),
            })
        values = report_base_values(
            self.env, docids, 'account.payment', payments,
            'Payment',
            'Print Payment · Landscape',
        )
        values['entries'] = docs
        return values


def _purchase_entries(env, orders):
    docs = []
    for order in orders:
        project = first_project(order)
        rows = []
        for line in order.order_line:
            if line.display_type in ('line_section', 'line_note'):
                continue
            rows.append({
                'product': line.product_id.display_name or '',
                'name': line.name or '',
                'qty': line.product_qty,
                'uom': line.product_uom.display_name if line.product_uom else '',
                'price': line.price_unit,
                'subtotal': line.price_subtotal,
            })
        docs.append({
            'record': order,
            'lines': rows,
            'project_name': project.display_name if project else '',
            'state_label': selection_label(order, 'state'),
            'currency': order.currency_id or order.company_id.currency_id or env.company.currency_id,
        })
    return docs


class ReportRfq(models.AbstractModel):
    _name = 'report.ages_reports.rfq'
    _description = 'RFQ Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        orders = self.env['purchase.order'].browse(docids)
        values = report_base_values(
            self.env, docids, 'purchase.order', orders,
            'Request for Quotation',
            'Print RFQ · Landscape',
        )
        values['entries'] = _purchase_entries(self.env, orders)
        return values


class ReportPurchaseOrder(models.AbstractModel):
    _name = 'report.ages_reports.purchase_order'
    _description = 'Purchase Order Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        orders = self.env['purchase.order'].browse(docids)
        values = report_base_values(
            self.env, docids, 'purchase.order', orders,
            'Purchase Order',
            'Print PO · Landscape',
        )
        values['entries'] = _purchase_entries(self.env, orders)
        return values


class ReportReceipt(models.AbstractModel):
    _name = 'report.ages_reports.receipt'
    _description = 'Receipt Print'

    @api.model
    def _get_report_values(self, docids, data=None):
        pickings = self.env['stock.picking'].browse(docids)
        docs = []
        for picking in pickings:
            project = first_project(picking)
            rows = []
            moves = picking.move_ids
            for move in moves:
                qty_done = move.quantity if 'quantity' in move._fields else move.quantity_done
                rows.append({
                    'product': move.product_id.display_name or '',
                    'name': move.description_picking or move.name or '',
                    'demand': move.product_uom_qty,
                    'done': qty_done,
                    'uom': move.product_uom.display_name if move.product_uom else '',
                    'from_location': move.location_id.display_name or '',
                    'to_location': move.location_dest_id.display_name or '',
                })
            docs.append({
                'record': picking,
                'lines': rows,
                'project_name': project.display_name if project else '',
                'state_label': selection_label(picking, 'state'),
            })
        values = report_base_values(
            self.env, docids, 'stock.picking', pickings,
            'Receipt',
            'Print Receipt · Landscape',
        )
        values['entries'] = docs
        return values

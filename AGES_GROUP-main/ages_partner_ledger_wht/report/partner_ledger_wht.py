# -*- coding: utf-8 -*-

from odoo.addons.ages_custom_reports.report.partner_ledger_engine import PartnerLedgerEngine
from odoo.tools.float_utils import float_is_zero


def _ages_payment_from_move(move):
    return move.origin_payment_id if 'origin_payment_id' in move._fields else move.env['account.payment']


def _ages_payment_wht_amount(self, move):
    """Withholding amount posted on the payment (always positive)."""
    payment = _ages_payment_from_move(move)
    if not payment or not payment.should_withhold_tax:
        return 0.0
    tax = abs(sum(payment.withholding_line_ids.mapped('amount')))
    return self.currency.round(tax) if tax else 0.0


def _ages_copy_child(child, **overrides):
    row = dict(child)
    row.update(overrides)
    return row


def _iter_merged_move_children(self, partner_id, move, lines, running_balance):
    """Net amount on the first row, withholding tax on a second row."""
    tax = _ages_payment_wht_amount(self, move)
    rounding = self.currency.rounding
    if float_is_zero(tax, precision_rounding=rounding):
        child, running_balance = self._merged_move_child(
            partner_id, move, lines, running_balance
        )
        yield child, running_balance
        return

    debit = self.currency.round(sum(lines.mapped('debit')))
    credit = self.currency.round(sum(lines.mapped('credit')))
    gross = debit if debit else credit
    if float_is_zero(gross, precision_rounding=rounding) or gross <= tax:
        child, running_balance = self._merged_move_child(
            partner_id, move, lines, running_balance
        )
        yield child, running_balance
        return

    net = self.currency.round(gross - tax)
    tax = self.currency.round(gross - net)
    base_child, _ignored = self._merged_move_child(
        partner_id, move, lines, running_balance
    )

    if debit:
        net_debit, net_credit = net, 0.0
        tax_debit, tax_credit = tax, 0.0
        net_delta, tax_delta = net, tax
    else:
        net_debit, net_credit = 0.0, net
        tax_debit, tax_credit = 0.0, tax
        net_delta, tax_delta = -net, -tax

    running_balance = self.currency.round(running_balance + net_delta)
    yield _ages_copy_child(
        base_child,
        id=f'move_{move.id}',
        debit=net_debit,
        credit=net_credit,
        balance=running_balance,
    ), running_balance

    running_balance = self.currency.round(running_balance + tax_delta)
    yield _ages_copy_child(
        base_child,
        id=f'move_{move.id}_wht',
        badge='WHT',
        debit=tax_debit,
        credit=tax_credit,
        balance=running_balance,
    ), running_balance


PartnerLedgerEngine._iter_merged_move_children = _iter_merged_move_children

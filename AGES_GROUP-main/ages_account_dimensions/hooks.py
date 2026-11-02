# -*- coding: utf-8 -*-


def cancel_ages_srb_wht_refunds(env):
    """Cancel temporary AGES-SRB-WHT credit notes so they leave the ledgers."""
    Move = env['account.move']
    if hasattr(Move, '_ages_cancel_withheld_sales_tax_refunds'):
        return Move._ages_cancel_withheld_sales_tax_refunds()
    refunds = Move.search([
        ('move_type', '=', 'out_refund'),
        ('ref', '=like', 'AGES-SRB-WHT:%'),
        ('state', 'in', ('draft', 'posted')),
    ])
    for refund in refunds:
        refund.line_ids.remove_move_reconcile()
        if refund.state == 'posted':
            refund.button_draft()
        if refund.state == 'draft':
            refund.button_cancel()
    return refunds

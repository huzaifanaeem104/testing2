# -*- coding: utf-8 -*-


def revert_srb_withheld_credit_notes(env):
    """Cancel AGES-SRB-WHT credit notes created by the temporary 20/80 invoice fix."""
    refunds = env['account.move'].search([
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

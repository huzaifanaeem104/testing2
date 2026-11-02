# -*- coding: utf-8 -*-
"""Spend desk: PR → bill → retention, expenses, asset transfers."""

from odoo import _

from . import common as C


def build(desk, filters):
    env = desk.env
    filters = C.normalize_filters(env, filters)
    features = {
        'purchase_request': C.can_read(env, 'purchase.request'),
        'vendor_bill': C.can_read(env, 'account.move'),
        'bill_type': C.has_field(env, 'account.move', 'ages_bill_type'),
        'expense': C.can_read(env, 'ages.expense'),
        'asset_transfer': C.can_read(env, 'asset.transfer'),
    }
    queues = _queues(env, filters, features)
    selected = filters.get('queue_key') or (queues[0]['key'] if queues else False)
    active = next((q for q in queues if q['key'] == selected), queues[0] if queues else False)
    rows, columns = _rows(env, filters, active)
    inspector = False
    if filters.get('selected_id') and active:
        inspector = _inspector(env, filters, active, filters['selected_id'])
    return {
        'ok': True,
        'screen': 'spend',
        'queues': queues,
        'columns': columns,
        'rows': rows,
        'inspector': inspector,
        'features': features,
        'filters': filters,
        'active_queue': active['key'] if active else False,
    }


def _add(env, filters, items, key, label, model, domain, severity='normal'):
    if not C.can_read(env, model):
        return
    count = C.search_count(env, model, domain, filters)
    action = C.window_action(
        env, model,
        domain=C.combine(C.scope_domain(env, model, filters), domain),
        name=label,
    )
    items.append(C.queue_item(key, label, count, severity if count else 'normal', domain=domain, model=model, action=action))


def _queues(env, filters, features):
    items = []
    if features['purchase_request']:
        Request = env['purchase.request']
        states = dict(Request._fields['state'].selection)
        if 'to_approve' in states:
            _add(env, filters, items, 'pr_approve', _('Pending approval'), 'purchase.request',
                 [('state', '=', 'to_approve')], 'warning')
        if C.can_read(env, 'purchase.request.line') and 'qty_to_buy' in env['purchase.request.line']._fields:
            lines = C.search_ids(env, 'purchase.request.line', [('qty_to_buy', '=', True)], filters, limit=400)
            domain = [('id', 'in', lines.ids)] if lines else [('id', '=', 0)]
            action = C.window_action(env, 'purchase.request.line', domain=domain, name=_('Purchase quantity'))
            items.append(C.queue_item(
                'pr_qty', _('Purchase quantity'), len(lines),
                'warning' if lines else 'normal', domain=domain, model='purchase.request.line', action=action,
            ))
        _add(env, filters, items, 'pr_progress', _('PR in progress'), 'purchase.request',
             [('state', 'in', ('approved', 'in_progress'))])
    if features['vendor_bill']:
        _add(env, filters, items, 'bills_draft', _('Draft vendor bills'), 'account.move',
             [('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'draft')], 'warning')
        _add(env, filters, items, 'bills_unpaid', _('Unpaid vendor bills'), 'account.move',
             [('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
              ('payment_state', 'in', ('not_paid', 'partial'))], 'warning')
        if C.has_field(env, 'account.move', 'ages_is_retention_release'):
            _add(env, filters, items, 'bills_retention', _('Retention bills'), 'account.move',
                 [('move_type', 'in', ('in_invoice', 'in_refund')), ('ages_is_retention_release', '=', True)])
        if features['bill_type']:
            _add(env, filters, items, 'bills_subcontract', _('Subcontract bills'), 'account.move',
                 [('move_type', 'in', ('in_invoice', 'in_refund')), ('ages_bill_type', '=', 'subcontract')])
    if features['expense']:
        _add(env, filters, items, 'expense_new', _('New expenses'), 'ages.expense', [('state', '=', 'new')], 'warning')
        _add(env, filters, items, 'expense_confirmed', _('Confirmed expenses'), 'ages.expense',
             [('state', '=', 'confirmed')], 'warning')
    if features['asset_transfer']:
        _add(env, filters, items, 'asset_draft', _('Draft asset transfers'), 'asset.transfer',
             [('state', '=', 'draft')], 'warning')
        _add(env, filters, items, 'asset_confirmed', _('Confirmed asset transfers'), 'asset.transfer',
             [('state', '=', 'confirmed')])
    return items


def _rows(env, filters, queue):
    if not queue or not queue.get('model'):
        return [], []
    records = C.search_ids(env, queue['model'], queue.get('domain') or [], filters, limit=filters.get('limit') or C.ROW_LIMIT)
    columns = [
        {'key': 'name', 'label': _('Name')},
        {'key': 'status', 'label': _('Status')},
        {'key': 'amount_compact', 'label': _('Amount'), 'money': True},
        {'key': 'detail', 'label': _('Detail')},
    ]
    rows = []
    for rec in records:
        status = ''
        if 'state' in rec._fields:
            status = dict(rec._fields['state'].selection).get(rec.state, rec.state) or ''
        elif 'request_state' in rec._fields:
            status = dict(rec._fields['request_state'].selection).get(rec.request_state, rec.request_state) or ''
        amount = 0.0
        for fname in ('amount_total', 'total_amount', 'amount', 'price_subtotal', 'pending_qty_to_receive'):
            if fname in rec._fields:
                amount = rec[fname] or 0.0
                break
        detail = ''
        if 'partner_id' in rec._fields and rec.partner_id:
            detail = rec.partner_id.display_name
        elif 'vendor_id' in rec._fields and rec.vendor_id:
            detail = rec.vendor_id.display_name
        elif 'product_id' in rec._fields and rec.product_id:
            detail = rec.product_id.display_name
        row = {
            'id': rec.id,
            'model': rec._name,
            'name': rec.display_name,
            'status': status,
            'amount': amount,
            'detail': detail,
            'action': C.record_action(env, rec),
        }
        C.pack_money(env, row, ['amount'], filters)
        rows.append(row)
    return rows, columns


def _inspector(env, filters, queue, rec_id):
    if not queue or not C.can_read(env, queue['model']):
        return False
    record = env[queue['model']].browse(rec_id)
    if not record.exists():
        return False
    facts = [{'label': _('Name'), 'value': record.display_name}]
    if 'state' in record._fields:
        facts.append({
            'label': _('Status'),
            'value': dict(record._fields['state'].selection).get(record.state, record.state),
        })
    if 'ages_bill_type' in record._fields and record.ages_bill_type:
        facts.append({
            'label': _('Bill type'),
            'value': dict(record._fields['ages_bill_type'].selection).get(record.ages_bill_type, record.ages_bill_type),
        })
    amounts = {}
    for fname in ('amount_total', 'amount_residual', 'total_amount', 'amount'):
        if fname in record._fields:
            amounts[fname] = record[fname] or 0.0
    if amounts:
        C.pack_money(env, amounts, list(amounts), filters)
    return {
        'title': record.display_name,
        'kind': 'spend',
        'facts': facts,
        'amounts': amounts,
        'actions': [{'label': _('Open'), 'action': C.record_action(env, record)}],
    }

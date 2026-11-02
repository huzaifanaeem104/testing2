# -*- coding: utf-8 -*-
"""Books desk: JE validation, unposted JEs, WHT, budget, tax reminders."""

from odoo import _

from . import common as C


def build(desk, filters):
    env = desk.env
    filters = C.normalize_filters(env, filters)
    features = {
        'move': C.can_read(env, 'account.move'),
        'je_stage': C.has_field(env, 'account.move', 'je_stage'),
        'payment': C.can_read(env, 'account.payment'),
        'withholding': False,
        'budget': C.can_read(env, 'crossovered.budget.line') and C.has_field(env, 'crossovered.budget.line', 'is_above_budget'),
        'tax_reminders': bool(C.safe_ref(env, 'ages_custom_reports.tax_return_activity_type')),
    }
    if features['payment']:
        Payment = env['account.payment']
        features['withholding'] = any(
            name in Payment._fields
            for name in ('payment_withholding_line_ids', 'withholding_line_ids')
        )
    queues = _queues(env, filters, features)
    selected = filters.get('queue_key') or (queues[0]['key'] if queues else False)
    active = next((q for q in queues if q['key'] == selected), queues[0] if queues else False)
    rows, columns = _rows(env, filters, active)
    inspector = False
    if filters.get('selected_id') and active:
        inspector = _inspector(env, active, filters['selected_id'])
    return {
        'ok': True,
        'screen': 'books',
        'queues': queues,
        'columns': columns,
        'rows': rows,
        'inspector': inspector,
        'features': features,
        'filters': filters,
        'active_queue': active['key'] if active else False,
        'hint': _('Accounting operations. Financial statements stay in Custom Reports.'),
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
    if features['move']:
        if features['je_stage']:
            _add(env, filters, items, 'je_validate', _('JE validation'), 'account.move',
                 [('move_type', '=', 'entry'), ('je_stage', '=', 'validate')], 'warning')
        _add(env, filters, items, 'je_unposted', _('Unposted JEs'), 'account.move',
             [('move_type', '=', 'entry'), ('state', '=', 'draft')], 'warning')
    if features['withholding']:
        _add(env, filters, items, 'wht', _('Withholding tax'), 'account.payment',
             [('payment_type', '=', 'outbound'), ('state', 'in', ('draft', 'in_process'))], 'warning')
    if features['budget']:
        lines = C.search_ids(env, 'crossovered.budget.line', [], filters, limit=300)
        above = lines.filtered('is_above_budget')
        domain = [('id', 'in', above.ids)] if above else [('id', '=', 0)]
        action = C.window_action(env, 'crossovered.budget.line', domain=domain, name=_('Budget variance'))
        items.append(C.queue_item(
            'budget', _('Budget variance'), len(above),
            'danger' if above else 'normal', domain=domain, model='crossovered.budget.line', action=action,
        ))
    activity_type = C.safe_ref(env, 'ages_custom_reports.tax_return_activity_type')
    if features['tax_reminders'] and activity_type and C.can_read(env, 'mail.activity'):
        domain = [('activity_type_id', '=', activity_type.id)]
        count = C.search_count(env, 'mail.activity', domain, filters)
        items.append(C.queue_item(
            'tax_reminders', _('Tax reminders'), count, 'warning' if count else 'normal',
            domain=domain, model='mail.activity',
            action=C.window_action(env, 'mail.activity', domain=domain, name=_('Tax reminders')),
        ))
    return items


def _rows(env, filters, queue):
    if not queue or not queue.get('model'):
        return [], []
    records = C.search_ids(env, queue['model'], queue.get('domain') or [], filters, limit=filters.get('limit') or C.ROW_LIMIT)
    columns = [
        {'key': 'name', 'label': _('Name')},
        {'key': 'status', 'label': _('Status')},
        {'key': 'date', 'label': _('Date')},
        {'key': 'amount_compact', 'label': _('Amount'), 'money': True},
    ]
    rows = []
    for rec in records:
        status = ''
        if 'je_stage' in rec._fields and rec.je_stage:
            status = dict(rec._fields['je_stage'].selection).get(rec.je_stage, rec.je_stage)
        elif 'state' in rec._fields:
            status = dict(rec._fields['state'].selection).get(rec.state, rec.state) or ''
        date_value = ''
        for fname in ('date', 'date_deadline', 'create_date'):
            if fname in rec._fields and rec[fname]:
                date_value = str(rec[fname])[:10]
                break
        amount = 0.0
        for fname in ('amount_total', 'amount', 'practical_amount'):
            if fname in rec._fields:
                amount = rec[fname] or 0.0
                break
        row = {
            'id': rec.id,
            'model': rec._name,
            'name': rec.display_name,
            'status': status,
            'date': date_value,
            'amount': amount,
            'action': C.record_action(env, rec),
        }
        C.pack_money(env, row, ['amount'], filters)
        rows.append(row)
    return rows, columns


def _inspector(env, queue, rec_id):
    if not queue or not C.can_read(env, queue['model']):
        return False
    record = env[queue['model']].browse(rec_id)
    if not record.exists():
        return False
    facts = [{'label': _('Name'), 'value': record.display_name}]
    for fname, label in (('state', _('Status')), ('je_stage', _('JE stage')), ('date', _('Date'))):
        if fname in record._fields and record[fname]:
            value = record[fname]
            if record._fields[fname].type == 'selection':
                value = dict(record._fields[fname].selection).get(value, value)
            facts.append({'label': label, 'value': value})
    return {
        'title': record.display_name,
        'kind': 'books',
        'facts': facts,
        'actions': [{'label': _('Open'), 'action': C.record_action(env, record)}],
    }

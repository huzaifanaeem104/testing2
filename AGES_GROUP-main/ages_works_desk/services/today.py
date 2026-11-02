# -*- coding: utf-8 -*-
"""Today: exception inbox. No charts."""

from odoo import fields, _

from . import common as C

_CONSUMPTION_SCAN = 200


def build(desk, filters):
    env = desk.env
    filters = C.normalize_filters(env, filters)
    queues = []
    features = {}

    queues.append(_contracts_attention(env, filters))
    queues.append(_ra_capacity(env, filters))
    queues.append(_ra_draft(env, filters))
    queues.extend(_optional_gate(env, filters, features))
    queues.extend(_optional_quality(env, filters, features))
    queues.extend(_optional_purchase(env, filters, features))
    queues.extend(_optional_consumption(env, filters, features))
    queues.extend(_optional_expense(env, filters, features))
    queues.extend(_optional_assets(env, filters, features))
    queues.extend(_books_queues(env, filters, features))

    queues = [q for q in queues if q]
    selected = filters.get('queue_key') or (queues[0]['key'] if queues else False)
    active = next((q for q in queues if q['key'] == selected), queues[0] if queues else False)
    rows, columns = _rows_for_queue(env, filters, active)
    inspector = False
    if filters.get('selected_id') and active:
        inspector = _inspector_for(env, filters, active, filters['selected_id'])
    return {
        'ok': True,
        'screen': 'today',
        'queues': queues,
        'columns': columns,
        'rows': rows,
        'inspector': inspector,
        'features': features,
        'filters': filters,
        'active_queue': active['key'] if active else False,
    }


def _action(env, model, domain, xml_id=None, name=None):
    if xml_id:
        action = C.xml_action(env, xml_id, domain=domain, name=name)
        if action:
            return action
    return C.window_action(env, model, domain=domain, name=name)


def _contracts_attention(env, filters):
    if not C.can_read(env, 'ages.contract'):
        return False
    close_to = filters.get('date_to') or fields.Date.context_today(env.user)
    domain = [
        ('state', 'in', ('new', 'running')),
        ('date_close', '!=', False),
        ('date_close', '<=', close_to),
    ]
    count = C.search_count(env, 'ages.contract', domain, filters)
    return C.queue_item(
        'contracts_attention',
        _('Contracts requiring attention'),
        count,
        'warning' if count else 'normal',
        domain=domain,
        model='ages.contract',
        action=_action(env, 'ages.contract', C.combine(C.scope_domain(env, 'ages.contract', filters), domain),
                       'ages_contracts_menu.action_ages_contract', _('Contracts requiring attention')),
    )


def _ra_capacity(env, filters):
    if not C.can_read(env, 'ages.contract'):
        return False
    contracts = C.search_ids(env, 'ages.contract', [('state', '=', 'running')], filters, limit=500)
    ids = [c.id for c in contracts if C.remaining_ra(c) > 0]
    domain = [('id', 'in', ids)] if ids else [('id', '=', 0)]
    return C.queue_item(
        'ra_capacity',
        _('RA billing capacity'),
        len(ids),
        'normal',
        domain=domain,
        model='ages.contract',
        action=_action(env, 'ages.contract', domain, 'ages_contracts_menu.action_ages_contract', _('RA billing capacity')),
    )


def _ra_draft(env, filters):
    if not C.can_read(env, 'ages.running.bill'):
        return False
    domain = [('state', '=', 'draft')]
    count = C.search_count(env, 'ages.running.bill', domain, filters)
    return C.queue_item(
        'ra_draft',
        _('RA / billing exceptions'),
        count,
        'warning' if count else 'normal',
        domain=domain,
        model='ages.running.bill',
        action=_action(env, 'ages.running.bill', C.combine(C.scope_domain(env, 'ages.running.bill', filters), domain),
                       'ages_contracts_menu.action_ages_running_bill', _('Draft running bills')),
    )


def _optional_gate(env, filters, features):
    items = []
    if not C.can_read(env, 'ages.gate.pass'):
        features['gate'] = False
        return items
    features['gate'] = True
    Gate = env['ages.gate.pass']
    states = dict(Gate._fields['state'].selection) if 'state' in Gate._fields else {}
    if 'waiting_security' in states:
        domain = [('state', '=', 'waiting_security')]
        count = C.search_count(env, 'ages.gate.pass', domain, filters)
        items.append(C.queue_item(
            'gate_waiting', _('Gate passes waiting'), count, 'warning' if count else 'normal',
            domain=domain, model='ages.gate.pass',
            action=_action(env, 'ages.gate.pass', C.combine(C.scope_domain(env, 'ages.gate.pass', filters), domain),
                           'ages_gate_pass.action_ages_gate_pass', _('Gate passes waiting')),
        ))
    if 'is_overdue' in Gate._fields:
        domain = [('is_overdue', '=', True)]
        count = C.search_count(env, 'ages.gate.pass', domain, filters)
        items.append(C.queue_item(
            'gate_overdue', _('Overdue gate passes'), count, 'danger' if count else 'normal',
            domain=domain, model='ages.gate.pass',
            action=_action(env, 'ages.gate.pass', C.combine(C.scope_domain(env, 'ages.gate.pass', filters), domain),
                           'ages_gate_pass.action_ages_gate_pass', _('Overdue gate passes')),
        ))
    return items


def _optional_quality(env, filters, features):
    items = []
    if C.can_read(env, 'quality.check') and 'quality_state' in env['quality.check']._fields:
        features['quality_check'] = True
        domain = [('quality_state', '=', 'fail')]
        count = C.search_count(env, 'quality.check', domain, filters)
        items.append(C.queue_item(
            'quality_fail', _('Quality failures'), count, 'danger' if count else 'normal',
            domain=domain, model='quality.check',
            action=_action(env, 'quality.check', C.combine(C.scope_domain(env, 'quality.check', filters), domain),
                           name=_('Quality failures')),
        ))
        todo = [('quality_state', '=', 'none')]
        todo_count = C.search_count(env, 'quality.check', todo, filters)
        items.append(C.queue_item(
            'quality_todo', _('Quality checks to do'), todo_count, 'warning' if todo_count else 'normal',
            domain=todo, model='quality.check',
            action=_action(env, 'quality.check', C.combine(C.scope_domain(env, 'quality.check', filters), todo),
                           name=_('Quality checks to do')),
        ))
    else:
        features['quality_check'] = False
    if C.can_read(env, 'quality.alert'):
        features['quality_alert'] = True
        domain = [('stage_id.done', '=', False)] if C.has_field(env, 'quality.alert.stage', 'done') else []
        count = C.search_count(env, 'quality.alert', domain, filters)
        items.append(C.queue_item(
            'quality_alerts', _('Open quality alerts'), count, 'warning' if count else 'normal',
            domain=domain, model='quality.alert',
            action=_action(env, 'quality.alert', C.combine(C.scope_domain(env, 'quality.alert', filters), domain),
                           name=_('Open quality alerts')),
        ))
    else:
        features['quality_alert'] = False
    return items


def _optional_purchase(env, filters, features):
    if not C.can_read(env, 'purchase.request'):
        features['purchase_request'] = False
        return []
    features['purchase_request'] = True
    Request = env['purchase.request']
    states = dict(Request._fields['state'].selection) if 'state' in Request._fields else {}
    items = []
    if 'to_approve' in states:
        domain = [('state', '=', 'to_approve')]
        count = C.search_count(env, 'purchase.request', domain, filters)
        items.append(C.queue_item(
            'pr_approve', _('Purchase requests awaiting approval'), count, 'warning' if count else 'normal',
            domain=domain, model='purchase.request',
            action=_action(env, 'purchase.request', C.combine(C.scope_domain(env, 'purchase.request', filters), domain),
                           name=_('Purchase requests awaiting approval')),
        ))
    return items


def _optional_consumption(env, filters, features):
    if not C.can_read(env, 'ages.material.consumption'):
        features['consumption'] = False
        return []
    features['consumption'] = True
    headers = C.search_ids(
        env, 'ages.material.consumption',
        [('state', 'in', ('draft', 'confirmed'))],
        filters, limit=_CONSUMPTION_SCAN,
    )
    short_ids = _insufficient_header_ids(headers)
    domain = [('id', 'in', short_ids)] if short_ids else [('id', '=', 0)]
    return [C.queue_item(
        'consumption_short', _('Insufficient consumption'), len(short_ids),
        'danger' if short_ids else 'normal',
        domain=domain, model='ages.material.consumption',
        action=_action(env, 'ages.material.consumption', domain, name=_('Insufficient consumption')),
    )]


def _insufficient_header_ids(headers):
    ids = []
    for header in headers:
        for line in header.line_ids:
            if (line.quantity or 0.0) > (line.available_qty or 0.0):
                ids.append(header.id)
                break
    return ids


def _optional_expense(env, filters, features):
    if not C.can_read(env, 'ages.expense'):
        features['expense'] = False
        return []
    features['expense'] = True
    domain = [('state', 'in', ('new', 'confirmed'))]
    count = C.search_count(env, 'ages.expense', domain, filters)
    return [C.queue_item(
        'expense', _('Expense exceptions'), count, 'warning' if count else 'normal',
        domain=domain, model='ages.expense',
        action=_action(env, 'ages.expense', C.combine(C.scope_domain(env, 'ages.expense', filters), domain),
                       name=_('Expense exceptions')),
    )]


def _optional_assets(env, filters, features):
    if not C.can_read(env, 'asset.transfer'):
        features['asset_transfer'] = False
        return []
    features['asset_transfer'] = True
    domain = [('state', 'in', ('draft', 'confirmed'))]
    count = C.search_count(env, 'asset.transfer', domain, filters)
    return [C.queue_item(
        'asset_transfer', _('Asset transfer exceptions'), count, 'warning' if count else 'normal',
        domain=domain, model='asset.transfer',
        action=_action(env, 'asset.transfer', C.combine(C.scope_domain(env, 'asset.transfer', filters), domain),
                       name=_('Asset transfer exceptions')),
    )]


def _books_queues(env, filters, features):
    items = []
    if C.can_read(env, 'account.move'):
        Move = env['account.move']
        if 'je_stage' in Move._fields:
            features['je_stage'] = True
            domain = [('move_type', '=', 'entry'), ('je_stage', '=', 'validate')]
            count = C.search_count(env, 'account.move', domain, filters)
            items.append(C.queue_item(
                'je_validate', _('JE validation'), count, 'warning' if count else 'normal',
                domain=domain, model='account.move',
                action=_action(env, 'account.move', C.combine(C.scope_domain(env, 'account.move', filters), domain),
                               name=_('Journal entries to validate')),
            ))
        else:
            features['je_stage'] = False
        unposted = [('move_type', '=', 'entry'), ('state', '=', 'draft')]
        count = C.search_count(env, 'account.move', unposted, filters)
        items.append(C.queue_item(
            'je_unposted', _('Unposted journal entries'), count, 'warning' if count else 'normal',
            domain=unposted, model='account.move',
            action=_action(env, 'account.move', C.combine(C.scope_domain(env, 'account.move', filters), unposted),
                           name=_('Unposted journal entries')),
        ))
    if C.can_read(env, 'account.payment'):
        Payment = env['account.payment']
        wht_field = False
        for name in ('payment_withholding_line_ids', 'withholding_line_ids'):
            if name in Payment._fields:
                wht_field = name
                break
        if wht_field:
            features['withholding'] = True
            domain = [('payment_type', '=', 'outbound'), ('state', 'in', ('draft', 'in_process'))]
            count = C.search_count(env, 'account.payment', domain, filters)
            items.append(C.queue_item(
                'wht', _('Withholding-tax actions'), count, 'warning' if count else 'normal',
                domain=domain, model='account.payment',
                action=_action(env, 'account.payment', C.combine(C.scope_domain(env, 'account.payment', filters), domain),
                               name=_('Withholding-tax actions')),
            ))
        else:
            features['withholding'] = False
    if C.can_read(env, 'crossovered.budget.line') and 'is_above_budget' in env['crossovered.budget.line']._fields:
        features['budget'] = True
        lines = C.search_ids(env, 'crossovered.budget.line', [], filters, limit=300)
        above = lines.filtered('is_above_budget')
        domain = [('id', 'in', above.ids)] if above else [('id', '=', 0)]
        items.append(C.queue_item(
            'budget', _('Budget variance'), len(above), 'danger' if above else 'normal',
            domain=domain, model='crossovered.budget.line',
            action=_action(env, 'crossovered.budget.line', domain, name=_('Budget variance')),
        ))
    else:
        features['budget'] = False
    activity_type = C.safe_ref(env, 'ages_custom_reports.tax_return_activity_type')
    if activity_type and C.can_read(env, 'mail.activity'):
        features['tax_reminders'] = True
        domain = [('activity_type_id', '=', activity_type.id)]
        count = C.search_count(env, 'mail.activity', domain, filters)
        items.append(C.queue_item(
            'tax_reminders', _('Tax reminders'), count, 'warning' if count else 'normal',
            domain=domain, model='mail.activity',
            action=_action(env, 'mail.activity', domain, name=_('Tax reminders')),
        ))
    else:
        features['tax_reminders'] = False
    return items


def _rows_for_queue(env, filters, queue):
    if not queue or not queue.get('model') or not C.can_read(env, queue['model']):
        return [], []
    model = queue['model']
    records = C.search_ids(env, model, queue.get('domain') or [], filters, limit=filters.get('limit') or C.ROW_LIMIT)
    columns = [{'key': 'name', 'label': _('Name')}, {'key': 'status', 'label': _('Status')}]
    if model == 'ages.contract':
        columns.append({'key': 'remaining_ra_compact', 'label': _('Remaining RA'), 'money': True})
    rows = []
    for rec in records:
        status = C.selection_label(rec, 'state') or C.selection_label(rec, 'quality_state')
        row = {
            'id': rec.id,
            'model': model,
            'name': rec.display_name,
            'status': status,
            'action': C.record_action(env, rec),
        }
        if model == 'ages.contract':
            remaining = C.remaining_ra(rec)
            row['remaining_ra'] = remaining
            C.pack_money(env, row, ['remaining_ra'], filters)
        rows.append(row)
    return rows, columns


def _inspector_for(env, filters, queue, rec_id):
    if not queue or not queue.get('model') or not C.can_read(env, queue['model']):
        return False
    record = env[queue['model']].browse(rec_id)
    if not record.exists():
        return False
    facts = [
        {'label': _('Name'), 'value': record.display_name},
    ]
    if 'state' in record._fields:
        facts.append({
            'label': _('Status'),
            'value': dict(record._fields['state'].selection).get(record.state, record.state),
        })
    return {
        'title': record.display_name,
        'kind': 'today',
        'facts': facts,
        'actions': [a for a in [
            {'label': _('Open'), 'action': C.record_action(env, record)},
            {'label': _('Open queue'), 'action': queue.get('action')},
        ] if a.get('action')],
    }

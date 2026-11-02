# -*- coding: utf-8 -*-
"""Contracts working table, remaining RA capacity, A–I inspector."""

from odoo import _

from . import common as C

RA_WATERFALL = (
    ('A', 'value_of_work_done', 'Value of Work Done'),
    ('B', 'rebate_amount', 'Rebate'),
    ('C', 'ex_rebate_value', 'Ex Rebate Value'),
    ('D', 'material_recovery', 'Material Recovery'),
    ('E', 'ex_rebate_mr_value', 'Ex Rebate & MR'),
    ('F', 'sales_tax_amount', 'Sales Tax'),
    ('H', 'mobilization_amount', 'Mobilization'),
    ('I', 'retention_amount', 'Retention'),
)


def build(desk, filters):
    env = desk.env
    filters = C.normalize_filters(env, filters)
    if not C.can_read(env, 'ages.contract'):
        return C.empty_payload(filters, {'screen': 'contracts'})

    queues = _queues(env, filters)
    selected = filters.get('queue_key') or 'remaining'
    active = next((q for q in queues if q['key'] == selected), queues[0])
    rows = _table_rows(env, filters, active)
    inspector = False
    if filters.get('selected_id'):
        inspector = inspect(desk, filters, filters['selected_id'])
    return {
        'ok': True,
        'screen': 'contracts',
        'queues': queues,
        'columns': _columns(),
        'rows': rows,
        'inspector': inspector,
        'features': {
            'mobilization_payment': C.has_field(env, 'ages.mobilization.advance', 'amount_remaining'),
            'retention_payment': C.has_field(env, 'ages.retention.recovery', 'amount_remaining'),
        },
        'filters': filters,
        'active_queue': active['key'],
        'sort_key': filters.get('sort_key') or 'remaining_ra',
        'sort_dir': filters.get('sort_dir') or 'desc',
    }


def _columns():
    return [
        {'key': 'name', 'label': _('Contract')},
        {'key': 'partner', 'label': _('Customer')},
        {'key': 'project', 'label': _('Project')},
        {'key': 'sub_company', 'label': _('Sub Company')},
        {'key': 'contract_value_compact', 'label': _('Contract Value'), 'money': True, 'sort': 'contract_value'},
        {'key': 'ra_work_compact', 'label': _('RA Work'), 'money': True, 'sort': 'ra_work'},
        {'key': 'remaining_ra_compact', 'label': _('Remaining RA Capacity'), 'money': True, 'sort': 'remaining_ra'},
        {'key': 'mobilization_compact', 'label': _('Mobilization'), 'money': True},
        {'key': 'retention_compact', 'label': _('Retention'), 'money': True},
        {'key': 'ra_status', 'label': _('RA Status')},
        {'key': 'close_date', 'label': _('Close Date')},
    ]


def _queues(env, filters):
    running = C.search_ids(env, 'ages.contract', [('state', '=', 'running')], filters, limit=500)
    with_cap = running.filtered(lambda c: C.remaining_ra(c) > 0)
    no_cap = running.filtered(lambda c: C.remaining_ra(c) <= 0)
    closing = C.search_ids(env, 'ages.contract', [('state', '=', 'running'), ('date_close', '!=', False)], filters, limit=500)
    new = C.search_count(env, 'ages.contract', [('state', '=', 'new')], filters)
    draft_ra = C.search_count(env, 'ages.running.bill', [('state', '=', 'draft')], filters)

    def act(domain, name):
        return C.xml_action(env, 'ages_contracts_menu.action_ages_contract', domain=domain, name=name) or \
            C.window_action(env, 'ages.contract', domain=domain, name=name)

    return [
        C.queue_item('remaining', _('Remaining RA'), len(with_cap), 'normal',
                     domain=[('id', 'in', with_cap.ids)] if with_cap else [('id', '=', 0)],
                     model='ages.contract', action=act([('id', 'in', with_cap.ids)] if with_cap else [('id', '=', 0)], _('Remaining RA'))),
        C.queue_item('covered', _('Fully billed (running)'), len(no_cap), 'warning' if no_cap else 'normal',
                     domain=[('id', 'in', no_cap.ids)] if no_cap else [('id', '=', 0)],
                     model='ages.contract', action=act([('id', 'in', no_cap.ids)] if no_cap else [('id', '=', 0)], _('Fully billed'))),
        C.queue_item('new', _('New'), new, 'normal',
                     domain=[('state', '=', 'new')], model='ages.contract',
                     action=act(C.combine(C.scope_domain(env, 'ages.contract', filters), [('state', '=', 'new')]), _('New contracts'))),
        C.queue_item('closing', _('Has close date'), len(closing), 'warning' if closing else 'normal',
                     domain=[('id', 'in', closing.ids)] if closing else [('id', '=', 0)],
                     model='ages.contract', action=act([('id', 'in', closing.ids)] if closing else [('id', '=', 0)], _('Closing'))),
        C.queue_item('ra_draft', _('Draft RA bills'), draft_ra, 'warning' if draft_ra else 'normal',
                     domain=[('state', '=', 'draft')], model='ages.running.bill',
                     action=C.xml_action(env, 'ages_contracts_menu.action_ages_running_bill',
                                         domain=C.combine(C.scope_domain(env, 'ages.running.bill', filters), [('state', '=', 'draft')]),
                                         name=_('Draft RA bills'))),
    ]


def _table_rows(env, filters, queue):
    domain = queue.get('domain') or []
    if queue.get('key') == 'ra_draft':
        bills = C.search_ids(env, 'ages.running.bill', domain, filters, limit=500)
        contracts = bills.mapped('contract_id')
    else:
        contracts = C.search_ids(env, 'ages.contract', domain, filters, limit=500)
    rows = [_row(env, contract, filters) for contract in contracts]
    sort_key = filters.get('sort_key') or 'remaining_ra'
    reverse = (filters.get('sort_dir') or 'desc') == 'desc'
    rows.sort(key=lambda row: row.get(sort_key) or 0, reverse=reverse)
    return rows[: filters.get('limit') or C.ROW_LIMIT]


def _row(env, contract, filters):
    remaining = C.remaining_ra(contract)
    ra_work = (contract.total_work_done_value or 0) - remaining
    mobilization = contract.total_mobilization_amount if 'total_mobilization_amount' in contract._fields else 0.0
    retention = contract.total_retention_amount if 'total_retention_amount' in contract._fields else 0.0
    if remaining > 0:
        ra_status = _('Capacity')
    elif contract.state == 'running':
        ra_status = _('Covered')
    else:
        ra_status = C.selection_label(contract, 'state')
    row = {
        'id': contract.id,
        'model': 'ages.contract',
        'name': contract.display_name,
        'partner': contract.partner_id.display_name if contract.partner_id else '',
        'project': contract.project_id.display_name if contract.project_id else '',
        'sub_company': contract.sub_company_id.display_name if contract.sub_company_id else '',
        'state': contract.state,
        'state_label': C.selection_label(contract, 'state'),
        'contract_value': contract.total_work_done_value or 0,
        'ra_work': ra_work,
        'remaining_ra': remaining,
        'mobilization': mobilization or 0.0,
        'retention': retention or 0.0,
        'ra_status': ra_status,
        'close_date': str(contract.date_close) if contract.date_close else '',
        'action': C.record_action(env, contract, 'ages_contracts_menu.action_ages_contract'),
    }
    C.pack_money(env, row, ['contract_value', 'ra_work', 'remaining_ra', 'mobilization', 'retention'], filters)
    return row


def inspect(desk, filters, contract_id):
    env = desk.env
    filters = C.normalize_filters(env, filters)
    if not C.can_read(env, 'ages.contract'):
        return False
    contract = env['ages.contract'].browse(contract_id)
    if not contract.exists():
        return False
    remaining = C.remaining_ra(contract)
    bills = contract.running_bill_ids.filtered(lambda bill: bill.state != 'cancelled')
    waterfall = _waterfall(env, bills, filters)
    unpaid = _unpaid_invoices(env, contract, filters)
    mob = _linked_money(env, contract, 'mobilization_advance_id', filters)
    ret = _linked_money(env, contract, 'retention_recovery_id', filters)
    return {
        'title': contract.display_name,
        'kind': 'contract',
        'facts': [
            {'label': _('Customer'), 'value': contract.partner_id.display_name or ''},
            {'label': _('Project'), 'value': contract.project_id.display_name or ''},
            {'label': _('Sub Company'), 'value': contract.sub_company_id.display_name or ''},
            {'label': _('Status'), 'value': C.selection_label(contract, 'state')},
            {'label': _('Close Date'), 'value': str(contract.date_close) if contract.date_close else ''},
        ],
        'amounts': C.pack_money(env, {
            'contract_value': contract.total_work_done_value or 0,
            'ra_work': (contract.total_work_done_value or 0) - remaining,
            'remaining_ra': remaining,
        }, ['contract_value', 'ra_work', 'remaining_ra'], filters),
        'waterfall': waterfall,
        'bills': [_bill_row(env, bill, filters) for bill in bills[:20]],
        'unpaid_invoices': unpaid,
        'mobilization': mob,
        'retention': ret,
        'actions': [a for a in [
            {'label': _('Open contract'), 'action': C.record_action(env, contract, 'ages_contracts_menu.action_ages_contract')},
            {'label': _('Running bills'), 'action': C.xml_action(
                env, 'ages_contracts_menu.action_ages_running_bill',
                domain=[('contract_id', '=', contract.id)],
                context={'default_contract_id': contract.id},
                name=_('Running bills'),
            ) or C.window_action(env, 'ages.running.bill', domain=[('contract_id', '=', contract.id)], name=_('Running bills'))},
            {'label': _('Unpaid invoices'), 'action': unpaid.get('action') if unpaid else False},
        ] if a.get('action')],
    }


def _waterfall(env, bills, filters):
    totals = {letter: 0.0 for letter, _field, _label in RA_WATERFALL}
    net_total = 0.0
    receivable_total = 0.0
    for bill in bills:
        for letter, field_name, _label in RA_WATERFALL:
            if field_name in bill._fields:
                totals[letter] += bill[field_name] or 0.0
        if 'net_amount' in bill._fields:
            net_total += bill.net_amount or 0.0
        if 'total_receivable' in bill._fields:
            receivable_total += bill.total_receivable or 0.0
    steps = []
    for letter, _field, label in RA_WATERFALL:
        step = {'letter': letter, 'label': _(label), 'amount': totals[letter]}
        C.pack_money(env, step, ['amount'], filters)
        steps.append(step)
    extra = C.pack_money(env, {'net': net_total, 'receivable': receivable_total}, ['net', 'receivable'], filters)
    return {'steps': steps, 'net': extra}


def _bill_row(env, bill, filters):
    row = {
        'id': bill.id,
        'name': bill.display_name,
        'state': C.selection_label(bill, 'state'),
        'invoice_payment_state': C.selection_label(bill, 'invoice_payment_state'),
        'value_of_work_done': bill.value_of_work_done or 0.0,
        'action': C.record_action(env, bill, 'ages_contracts_menu.action_ages_running_bill'),
    }
    C.pack_money(env, row, ['value_of_work_done'], filters)
    return row


def _unpaid_invoices(env, contract, filters):
    if not C.can_read(env, 'account.move'):
        return False
    Move = env['account.move']
    domain = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]
    if 'ages_contract_id' in Move._fields:
        domain.append(('ages_contract_id', '=', contract.id))
    elif 'invoice_origin' in Move._fields:
        domain.append(('invoice_origin', '=', contract.name))
    else:
        return False
    moves = C.search_ids(env, 'account.move', domain, filters, limit=40)
    action = C.window_action(env, 'account.move', domain=domain, name=_('Unpaid invoices'), view_mode='list,form')
    rows = []
    for move in moves:
        row = {'id': move.id, 'name': move.display_name, 'amount_residual': move.amount_residual or 0.0,
               'action': C.record_action(env, move)}
        C.pack_money(env, row, ['amount_residual'], filters)
        rows.append(row)
    return {'count': len(moves), 'rows': rows, 'action': action}


def _linked_money(env, contract, field_name, filters):
    if field_name not in contract._fields:
        return False
    record = contract[field_name]
    if not record:
        return False
    payload = {
        'id': record.id,
        'name': record.display_name,
        'action': C.record_action(env, record),
    }
    for name in ('amount_remaining', 'payment_state', 'amount'):
        if name in record._fields:
            payload[name] = record[name]
    if 'amount_remaining' in payload:
        C.pack_money(env, payload, ['amount_remaining'], filters)
    return payload

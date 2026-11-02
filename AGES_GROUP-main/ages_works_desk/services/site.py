# -*- coding: utf-8 -*-
"""Site desk: stock, gate, quality, consumption, people for a project."""

from odoo import fields, _

from . import common as C
from .today import _insufficient_header_ids


def build(desk, filters):
    env = desk.env
    filters = C.normalize_filters(env, filters)
    project = False
    if filters.get('project_ids') and C.can_read(env, 'project.project'):
        project = env['project.project'].browse(filters['project_ids'][:1]).exists()
        project = project[:1]
    features = {
        'stock': C.can_read(env, 'stock.quant'),
        'gate': C.can_read(env, 'ages.gate.pass'),
        'quality_check': C.can_read(env, 'quality.check'),
        'quality_alert': C.can_read(env, 'quality.alert'),
        'consumption': C.can_read(env, 'ages.material.consumption'),
        'people': C.can_read(env, 'hr.attendance'),
    }
    if not project:
        return {
            'ok': True,
            'screen': 'site',
            'queues': [],
            'columns': [],
            'rows': [],
            'inspector': False,
            'features': features,
            'filters': filters,
            'hint': _('Select a project to inspect this site.'),
            'active_queue': False,
        }

    queues = _queues(env, filters, project, features)
    selected = filters.get('queue_key') or (queues[0]['key'] if queues else False)
    active = next((q for q in queues if q['key'] == selected), queues[0] if queues else False)
    rows, columns = _rows(env, filters, active)
    inspector = False
    if filters.get('selected_id') and active:
        inspector = _inspector(env, active, filters['selected_id'])
    return {
        'ok': True,
        'screen': 'site',
        'project': C.named(project),
        'queues': queues,
        'columns': columns,
        'rows': rows,
        'inspector': inspector,
        'features': features,
        'filters': filters,
        'hint': False,
        'active_queue': active['key'] if active else False,
    }


def _project_domain(env, model_name, project):
    field_name = C.PROJECT_FIELD_MAP.get(model_name)
    if field_name and C.has_field(env, model_name, field_name.split('.')[0]):
        return [(field_name, '=', project.id)]
    if model_name == 'ages.gate.pass' and C.has_field(env, 'ages.gate.pass', 'picking_id'):
        picking_field = False
        Picking = env['stock.picking']
        if 'ages_project_id' in Picking._fields:
            picking_field = 'ages_project_id'
        elif C.has_field(env, 'stock.location', 'ages_project_id'):
            return [('picking_id.location_id.ages_project_id', '=', project.id)]
        if picking_field:
            return [('picking_id.%s' % picking_field, '=', project.id)]
    if model_name in ('quality.check', 'quality.alert') and C.has_field(env, model_name, 'picking_id'):
        if C.has_field(env, 'stock.location', 'ages_project_id'):
            return [('picking_id.location_id.ages_project_id', '=', project.id)]
    return []


def _queues(env, filters, project, features):
    items = []

    def add(key, label, model, domain, severity='normal', xml_id=None):
        if not C.can_read(env, model):
            return
        extra = _project_domain(env, model, project)
        full = C.combine(domain, extra)
        count = C.search_count(env, model, full, filters)
        action = C.xml_action(env, xml_id, domain=C.combine(C.scope_domain(env, model, filters), full), name=label) if xml_id else False
        action = action or C.window_action(env, model, domain=C.combine(C.scope_domain(env, model, filters), full), name=label)
        items.append(C.queue_item(key, label, count, severity if count else 'normal', domain=full, model=model, action=action))

    if features['gate']:
        Gate = env['ages.gate.pass']
        states = dict(Gate._fields['state'].selection)
        if 'waiting_security' in states:
            add('gate_waiting', _('Gate waiting'), 'ages.gate.pass', [('state', '=', 'waiting_security')],
                'warning', 'ages_gate_pass.action_ages_gate_pass')
        if 'is_overdue' in Gate._fields:
            add('gate_overdue', _('Gate overdue'), 'ages.gate.pass', [('is_overdue', '=', True)],
                'danger', 'ages_gate_pass.action_ages_gate_pass')
        add('gate_all', _('Gate passes'), 'ages.gate.pass', [], 'normal', 'ages_gate_pass.action_ages_gate_pass')
    if features['quality_check'] and 'quality_state' in env['quality.check']._fields:
        add('quality_fail', _('Quality failed'), 'quality.check', [('quality_state', '=', 'fail')], 'danger')
        add('quality_todo', _('Quality to do'), 'quality.check', [('quality_state', '=', 'none')], 'warning')
    if features['quality_alert']:
        domain = [('stage_id.done', '=', False)] if C.has_field(env, 'quality.alert.stage', 'done') else []
        add('quality_alerts', _('Open quality alerts'), 'quality.alert', domain, 'warning')
    if features['consumption']:
        headers = C.search_ids(
            env, 'ages.material.consumption',
            C.combine([('state', 'in', ('draft', 'confirmed'))], _project_domain(env, 'ages.material.consumption', project)),
            filters, limit=200,
        )
        short_ids = _insufficient_header_ids(headers)
        domain = [('id', 'in', short_ids)] if short_ids else [('id', '=', 0)]
        action = C.window_action(env, 'ages.material.consumption', domain=domain, name=_('Insufficient consumption'))
        items.append(C.queue_item(
            'consumption_short', _('Insufficient consumption'), len(short_ids),
            'danger' if short_ids else 'normal', domain=domain, model='ages.material.consumption', action=action,
        ))
        add('consumption_all', _('Consumption'), 'ages.material.consumption', [])
    if features['stock'] and C.has_field(env, 'stock.quant', 'quantity'):
        add('stock', _('Stock on hand'), 'stock.quant', [('quantity', '>', 0)])
    if features['people']:
        today = fields.Date.context_today(env.user)
        add('people', _('People on site'), 'hr.attendance', [('check_in', '>=', today)])
    return items


def _rows(env, filters, queue):
    if not queue or not queue.get('model'):
        return [], []
    records = C.search_ids(env, queue['model'], queue.get('domain') or [], filters, limit=filters.get('limit') or C.ROW_LIMIT)
    columns = [
        {'key': 'name', 'label': _('Name')},
        {'key': 'status', 'label': _('Status')},
        {'key': 'detail', 'label': _('Detail')},
    ]
    rows = []
    for rec in records:
        status = ''
        if 'state' in rec._fields:
            status = dict(rec._fields['state'].selection).get(rec.state, rec.state) or ''
        elif 'quality_state' in rec._fields:
            status = dict(rec._fields['quality_state'].selection).get(rec.quality_state, rec.quality_state) or ''
        detail = ''
        if 'product_id' in rec._fields and rec.product_id:
            detail = rec.product_id.display_name
        elif 'partner_id' in rec._fields and rec.partner_id:
            detail = rec.partner_id.display_name
        elif 'employee_id' in rec._fields and rec.employee_id:
            detail = rec.employee_id.display_name
        rows.append({
            'id': rec.id,
            'model': rec._name,
            'name': rec.display_name,
            'status': status,
            'detail': detail,
            'action': C.record_action(env, rec),
        })
    return rows, columns


def _inspector(env, queue, rec_id):
    if not queue or not C.can_read(env, queue['model']):
        return False
    record = env[queue['model']].browse(rec_id)
    if not record.exists():
        return False
    facts = [{'label': _('Name'), 'value': record.display_name}]
    for fname, label in (
        ('state', _('Status')),
        ('quality_state', _('Quality')),
        ('quantity', _('Quantity')),
        ('available_qty', _('Available')),
        ('gate_type', _('Type')),
    ):
        if fname in record._fields:
            value = record[fname]
            if fname in ('state', 'quality_state', 'gate_type') and record._fields[fname].type == 'selection':
                value = dict(record._fields[fname].selection).get(value, value)
            facts.append({'label': label, 'value': value})
    return {
        'title': record.display_name,
        'kind': 'site',
        'facts': facts,
        'actions': [{'label': _('Open'), 'action': C.record_action(env, record)}],
    }

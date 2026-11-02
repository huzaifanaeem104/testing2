# -*- coding: utf-8 -*-
"""Shared ACL, filters, money formatting, and native action helpers for AGES Works."""

import itertools
import logging

from psycopg2.extensions import TRANSACTION_STATUS_INERROR

from odoo.osv import expression
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)
_SAVEPOINT = itertools.count()

ROW_LIMIT = 80

# (legal company field, sub-company field). Missing fields are skipped.
COMPANY_FIELD_MAP = {
    'ages.sub.company': ('company_id', 'id'),
    'project.project': ('company_id', 'ages_sub_company_id'),
    'ages.contract': ('company_id', 'sub_company_id'),
    'ages.running.bill': ('company_id', 'sub_company_id'),
    'ages.mobilization.advance': ('company_id', 'sub_company_id'),
    'ages.retention.recovery': ('company_id', 'sub_company_id'),
    'account.move': ('company_id', 'ages_sub_company_id'),
    'account.move.line': ('company_id', 'move_id.ages_sub_company_id'),
    'account.payment': ('company_id', 'ages_sub_company_id'),
    'ages.expense': ('company_id', 'sub_company_id'),
    'ages.material.consumption': ('company_id', 'sub_company_id'),
    'ages.material.consumption.line': ('company_id', 'consumption_id.sub_company_id'),
    'ages.gate.pass': ('company_id', 'sub_company_id'),
    'purchase.order': ('company_id', False),
    'purchase.request': ('company_id', False),
    'purchase.request.line': ('company_id', False),
    'stock.picking': ('company_id', False),
    'stock.quant': ('company_id', False),
    'quality.check': ('company_id', False),
    'quality.alert': ('company_id', False),
    'hr.attendance': ('employee_id.company_id', False),
    'asset.transfer': ('company_id', False),
    'crossovered.budget.line': ('company_id', False),
    'mail.activity': (False, False),
}

PROJECT_FIELD_MAP = {
    'project.project': 'id',
    'ages.contract': 'project_id',
    'ages.running.bill': 'project_id',
    'ages.mobilization.advance': 'project_id',
    'ages.retention.recovery': 'project_id',
    'account.move': 'ages_project_id',
    'account.payment': 'ages_project_id',
    'ages.expense': 'line_ids.project_id',
    'ages.material.consumption': 'project_id',
    'ages.material.consumption.line': 'consumption_id.project_id',
    'purchase.request': 'ages_project_id',
    'purchase.request.line': 'request_id.ages_project_id',
    'hr.attendance': 'employee_id.project_id',
    'asset.transfer': 'project_id',
    'stock.quant': 'location_id.ages_project_id',
}

CONTRACT_FIELD_MAP = {
    'ages.contract': 'id',
    'ages.running.bill': 'contract_id',
    'ages.mobilization.advance': 'contract_id',
    'ages.retention.recovery': 'contract_id',
    'account.move': 'ages_contract_id',
    'account.payment': 'ages_contract_id',
}

PARTNER_FIELD_MAP = {
    'ages.contract': 'partner_id',
    'ages.running.bill': 'partner_id',
    'ages.mobilization.advance': 'partner_id',
    'ages.retention.recovery': 'partner_id',
    'account.move': 'partner_id',
    'account.payment': 'partner_id',
    'ages.expense': 'vendor_id',
    'purchase.order': 'partner_id',
    'ages.gate.pass': 'partner_id',
}

DATE_FIELD_CANDIDATES = (
    'date', 'invoice_date', 'date_start', 'date_close', 'pass_date',
    'request_date', 'date_order', 'create_date',
)


def _guarded(env, default, func):
    """Run func inside a savepoint, including swallowed SQL errors from other modules."""
    name = 'awd_%s' % next(_SAVEPOINT)
    cr = env.cr
    cr.execute('SAVEPOINT %s' % name)
    try:
        result = func()
        if cr._cnx.get_transaction_status() == TRANSACTION_STATUS_INERROR:
            cr.execute('ROLLBACK TO SAVEPOINT %s' % name)
            return default
        cr.execute('RELEASE SAVEPOINT %s' % name)
        return result
    except Exception as exc:
        try:
            cr.execute('ROLLBACK TO SAVEPOINT %s' % name)
        except Exception:
            pass
        _logger.warning('Works Desk skipped operation: %s', exc)
        return default


def can_read(env, model_name):
    """True when the model exists and the current user may read it."""
    if not model_name or model_name not in env:
        return False
    Model = env[model_name]

    def _check():
        if hasattr(Model, 'has_access'):
            return bool(Model.has_access('read'))
        Model.check_access_rights('read')
        return True

    return bool(_guarded(env, False, _check))


def has_field(env, model_name, field_name):
    if not can_read(env, model_name):
        return False
    return field_name in env[model_name]._fields


def model_record(env, model_name):
    """ir.model lookup used for optional-module detection (sudo for metadata only)."""
    if not model_name:
        return env['ir.model']
    return env['ir.model'].sudo()._get(model_name)


def id_list(value, allow_zero=False):
    if value in (None, False, ''):
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result = []
    for item in values:
        try:
            item = int(item)
        except (TypeError, ValueError):
            continue
        if item > 0 or (allow_zero and item == 0):
            if item not in result:
                result.append(item)
    return result


def first_id(value):
    values = id_list(value)
    return values[0] if values else False


def normalize_filters(env, filters=None):
    raw = dict(filters or {})
    company_ids = id_list(raw.get('company_ids'), allow_zero=True)
    if not company_ids and 'company_ids' not in raw:
        company_ids = list(env.companies.ids)
    sub_ids = id_list(raw.get('sub_company_ids') or raw.get('ages_sub_company_id'))
    project_ids = id_list(raw.get('project_ids') or raw.get('project_id'))
    contract_ids = id_list(raw.get('contract_ids') or raw.get('contract_id'))
    partner_ids = id_list(raw.get('partner_ids') or raw.get('partner_id'))
    return {
        'company_ids': company_ids,
        'sub_company_ids': sub_ids,
        'project_ids': project_ids,
        'contract_ids': contract_ids,
        'partner_ids': partner_ids,
        'date_to': raw.get('date_to') or False,
        'queue_key': raw.get('queue_key') or False,
        'selected_id': first_id(raw.get('selected_id')),
        'sort_key': raw.get('sort_key') or False,
        'sort_dir': 'desc' if raw.get('sort_dir') == 'desc' else 'asc',
        'limit': int(raw.get('limit') or ROW_LIMIT),
    }


def _field_usable(Model, name):
    if not name:
        return False
    env = Model.env
    current = Model
    for part in name.split('.'):
        if part not in current._fields:
            return False
        field = current._fields[part]
        comodel = getattr(field, 'comodel_name', False)
        if comodel and comodel in env:
            current = env[comodel]
    return True


def scope_domain(env, model_name, filters):
    """Company / sub-company / project / contract / partner / date_to domain."""
    if not can_read(env, model_name):
        return [('id', '=', 0)]
    Model = env[model_name]
    domain = []
    company_field, sub_field = COMPANY_FIELD_MAP.get(model_name, ('company_id', False))
    if filters.get('company_ids') and _field_usable(Model, company_field):
        domain.append((company_field, 'in', filters['company_ids']))
    if filters.get('sub_company_ids') and _field_usable(Model, sub_field):
        domain.append((sub_field, 'in', filters['sub_company_ids']))
    project_field = PROJECT_FIELD_MAP.get(model_name)
    if filters.get('project_ids') and _field_usable(Model, project_field):
        domain.append((project_field, 'in', filters['project_ids']))
    contract_field = CONTRACT_FIELD_MAP.get(model_name)
    if filters.get('contract_ids') and _field_usable(Model, contract_field):
        domain.append((contract_field, 'in', filters['contract_ids']))
    partner_field = PARTNER_FIELD_MAP.get(model_name)
    if filters.get('partner_ids') and _field_usable(Model, partner_field):
        domain.append((partner_field, 'in', filters['partner_ids']))
    if filters.get('date_to'):
        date_field = next(
            (name for name in DATE_FIELD_CANDIDATES if name in Model._fields),
            False,
        )
        if date_field:
            domain.append((date_field, '<=', filters['date_to']))
    return domain


def combine(*domains):
    result = []
    for domain in domains:
        if domain:
            result = expression.AND([result, list(domain)]) if result else list(domain)
    return result or []


def _no_company(filters):
    company_ids = (filters or {}).get('company_ids')
    return bool(company_ids) and not any(cid > 0 for cid in company_ids)


def search_count(env, model_name, domain, filters=None):
    if not can_read(env, model_name) or _no_company(filters):
        return 0
    full = combine(scope_domain(env, model_name, filters or {}), domain)
    return _guarded(env, 0, lambda: env[model_name].search_count(full))


def search_ids(env, model_name, domain, filters=None, limit=ROW_LIMIT, order=None):
    empty = env[model_name] if model_name in env else env['ir.model']
    if not can_read(env, model_name) or _no_company(filters):
        return empty
    full = combine(scope_domain(env, model_name, filters or {}), domain)
    return _guarded(env, empty, lambda: env[model_name].search(full, limit=limit, order=order))


def safe_ref(env, xml_id):
    return _guarded(env, False, lambda: env.ref(xml_id, raise_if_not_found=False))


def selection_label(record, field_name):
    if not record or field_name not in record._fields:
        return ''
    field = record._fields[field_name]
    value = record[field_name]
    try:
        mapping = dict(field._description_selection(record.env) or [])
        return mapping.get(value, value) or ''
    except Exception:
        return value or ''


def currency_for(env, filters=None):
    company_ids = (filters or {}).get('company_ids') or env.companies.ids
    companies = env['res.company'].browse(company_ids).exists()
    currencies = companies.mapped('currency_id')
    return currencies[:1] or env.company.currency_id


def format_money(env, amount, filters=None):
    return formatLang(env, amount or 0.0, currency_obj=currency_for(env, filters))


def format_compact(env, amount, filters=None):
    """K/M compact PKR formatter (independent copy of Board display rules)."""
    amount = amount or 0.0
    currency = currency_for(env, filters)
    sign = '-' if amount < 0 else ''
    absolute = abs(amount)
    if absolute >= 1000000:
        body = '%.1f M' % (absolute / 1000000.0)
    elif absolute >= 1000:
        body = '%.1f K' % (absolute / 1000.0)
    else:
        body = formatLang(env, absolute, currency_obj=False)
    symbol = currency.symbol or ''
    if currency.position == 'after':
        return ('%s%s %s' % (sign, body, symbol)).strip()
    return ('%s%s %s' % (sign, symbol, body)).strip()


def pack_money(env, payload, keys, filters=None):
    for key in keys:
        value = payload.get(key) or 0.0
        payload['%s_display' % key] = format_money(env, value, filters)
        payload['%s_compact' % key] = format_compact(env, value, filters)
    return payload


def remaining_ra(contract):
    """Contract value minus non-cancelled RA work. Never negative."""
    bills = contract.running_bill_ids.filtered(lambda bill: bill.state != 'cancelled')
    used = sum(bills.mapped('value_of_work_done'))
    return max((contract.total_work_done_value or 0) - used, 0)


def named(record, extra=None):
    if not record:
        return False
    data = {'id': record.id, 'name': record.display_name}
    if extra:
        data.update(extra)
    return data


def xml_action(env, xml_id, domain=None, context=None, res_id=None, name=None):
    action = _guarded(env, False, lambda: env['ir.actions.actions']._for_xml_id(xml_id))
    if not action:
        return False
    if domain is not None:
        action['domain'] = domain
    ctx = action.get('context') or {}
    if isinstance(ctx, str):
        try:
            from odoo.tools.safe_eval import safe_eval
            ctx = safe_eval(ctx) or {}
        except Exception:
            ctx = {}
    ctx = dict(ctx)
    if context:
        ctx.update(context)
    action['context'] = ctx
    if res_id:
        action['res_id'] = res_id
        action['view_mode'] = 'form'
        action['views'] = [(False, 'form')]
    if name:
        action['name'] = name
    return action


def window_action(env, model_name, domain=None, res_id=None, name=None, view_mode='list,form', context=None):
    if not can_read(env, model_name):
        return False
    action = {
        'type': 'ir.actions.act_window',
        'res_model': model_name,
        'name': name or env[model_name]._description,
        'view_mode': view_mode,
        'views': [(False, mode) for mode in view_mode.split(',')],
        'target': 'current',
        'domain': domain or [],
        'context': context or {},
    }
    if res_id:
        action['res_id'] = res_id
        action['view_mode'] = 'form'
        action['views'] = [(False, 'form')]
    return action


def record_action(env, record, xml_id=None):
    if not record:
        return False
    if xml_id:
        action = xml_action(env, xml_id, res_id=record.id, name=record.display_name)
        if action:
            return action
    return window_action(env, record._name, res_id=record.id, name=record.display_name)


def queue_item(key, label, count, severity='normal', domain=None, model=None, action=None):
    return {
        'key': key,
        'label': label,
        'count': int(count or 0),
        'severity': severity if count else 'normal',
        'model': model or False,
        'domain': domain or [],
        'action': action or False,
    }


def filter_options(env, filters):
    company_ids = [cid for cid in (filters.get('company_ids') or env.companies.ids) if cid > 0]
    if not company_ids:
        company_ids = list(env.companies.ids)
    companies = env['res.company'].browse(company_ids).exists().sorted('name')
    if not companies:
        companies = env.companies.sorted('name')
        company_ids = list(companies.ids)

    sub_domain = [('company_id', 'in', company_ids)]
    if can_read(env, 'ages.sub.company'):
        subs = env['ages.sub.company'].search(sub_domain, order='name')
    else:
        subs = env['ages.sub.company']

    project_domain = [('company_id', 'in', company_ids)] if 'company_id' in env['project.project']._fields else []
    if filters.get('sub_company_ids') and has_field(env, 'project.project', 'ages_sub_company_id'):
        project_domain.append(('ages_sub_company_id', 'in', filters['sub_company_ids']))
    projects = env['project.project'].search(project_domain, order='name', limit=200) if can_read(env, 'project.project') else env['project.project']

    partner_domain = [('parent_id', '=', False), ('company_id', 'in', [False] + company_ids)]
    partners = env['res.partner'].search(partner_domain, order='name', limit=80) if can_read(env, 'res.partner') else env['res.partner']

    contract_domain = [('company_id', 'in', company_ids), ('state', '!=', 'cancelled')]
    if filters.get('sub_company_ids'):
        contract_domain.append(('sub_company_id', 'in', filters['sub_company_ids']))
    if filters.get('project_ids'):
        contract_domain.append(('project_id', 'in', filters['project_ids']))
    if filters.get('partner_ids'):
        contract_domain.append(('partner_id', 'in', filters['partner_ids']))
    contracts = env['ages.contract'].search(contract_domain, order='name desc', limit=200) if can_read(env, 'ages.contract') else env['ages.contract']

    return {
        'companies': [{'id': rec.id, 'name': rec.display_name} for rec in companies],
        'sub_companies': [{'id': rec.id, 'name': rec.display_name} for rec in subs],
        'projects': [{'id': rec.id, 'name': rec.display_name} for rec in projects],
        'partners': [{'id': rec.id, 'name': rec.display_name} for rec in partners],
        'contracts': [{'id': rec.id, 'name': rec.display_name} for rec in contracts],
        'filters': filters,
    }


def empty_payload(filters, extra=None):
    payload = {
        'ok': True,
        'queues': [],
        'columns': [],
        'rows': [],
        'inspector': False,
        'features': {},
        'filters': filters,
    }
    if extra:
        payload.update(extra)
    return payload

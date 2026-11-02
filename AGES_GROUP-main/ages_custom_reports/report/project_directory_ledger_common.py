# -*- coding: utf-8 -*-

from odoo import fields

HIDEABLE_ACCOUNT_PAYABLE_CODE = '211000'
HIDEABLE_COST_OF_REVENUE_CODE = '600000'
BANK_ACCOUNT_TYPES = ('asset_cash', 'liability_credit_card')
COST_OF_REVENUE_ACCOUNT_TYPES = ('expense_direct_cost',)


def primary_analytic_id_from_distribution(distribution):
    """Largest analytic share on this journal item. Empty means Uncategorized.

    Do not use ``list(dist)[0]``: mixed payment lines keep insertion order, so
    a 1% Deharki share written first would steal the whole cash line.
    """
    if not distribution:
        return False
    best_id = False
    best_pct = 0.0
    for raw_id, raw_pct in distribution.items():
        try:
            analytic_id = int(raw_id)
            percent = float(raw_pct or 0.0)
        except (TypeError, ValueError):
            continue
        if percent > best_pct:
            best_id = analytic_id
            best_pct = percent
    return best_id if best_pct > 0.0 else False


def resolve_line_project(line, cache):
    """Group PDL lines from this item's analytic_distribution only.

    Sibling / payment / header fallbacks are not used. On opening entry
    OPB/2026/09/0001, Cash at Site Alliance is tagged and Cash at Head
    Office is not — the untagged line must stay Uncategorized, not Alliance.
    """
    line_id = line.id
    if line_id in cache:
        return cache[line_id]
    Analytic = line.env['account.analytic.account']
    analytic_id = primary_analytic_id_from_distribution(line.analytic_distribution)
    analytic = Analytic.browse(analytic_id) if analytic_id else Analytic
    cache[line_id] = analytic
    return analytic


def apply_account_payable_visibility(move_lines, form):
    """When hide_account_payable is True (default), exclude 211000 lines."""
    if not form.get('hide_account_payable', True):
        return move_lines

    def _is_payable_line(line):
        return line.account_id and line.account_id.code == HIDEABLE_ACCOUNT_PAYABLE_CODE

    if hasattr(move_lines, 'filtered'):
        return move_lines.filtered(lambda line: not _is_payable_line(line))
    return [line for line in move_lines if not _is_payable_line(line)]


def _is_cost_of_revenue_line(line):
    account = line.account_id
    if not account:
        return False
    if account.code == HIDEABLE_COST_OF_REVENUE_CODE:
        return True
    return account.account_type in COST_OF_REVENUE_ACCOUNT_TYPES


def _is_bank_payment_line(line):
    account = line.account_id
    return bool(account and account.account_type in BANK_ACCOUNT_TYPES)


def apply_cost_of_revenue_visibility(move_lines, form):
    """When hide_cost_of_revenue is True (default), exclude Cost of Revenue lines."""
    if not form.get('hide_cost_of_revenue', True):
        return move_lines

    if hasattr(move_lines, 'filtered'):
        return move_lines.filtered(lambda line: not _is_cost_of_revenue_line(line))
    return [line for line in move_lines if not _is_cost_of_revenue_line(line)]


def apply_bank_visibility(move_lines, form):
    """When hide_bank is True (default), exclude bank / cash payment lines."""
    if not form.get('hide_bank', True):
        return move_lines

    if hasattr(move_lines, 'filtered'):
        return move_lines.filtered(lambda line: not _is_bank_payment_line(line))
    return [line for line in move_lines if not _is_bank_payment_line(line)]


def apply_target_move_domain(domain, form):
    """Append parent_state filter for Draft / Posted / All."""
    target_move = form.get('target_move') or 'posted'
    if target_move == 'posted':
        domain.append(('parent_state', '=', 'posted'))
    elif target_move == 'draft':
        domain.append(('parent_state', '=', 'draft'))
    return domain


def build_filter_labels(env, form):
    """Build human-readable filter criteria for report headers."""
    labels = []
    if form.get('sub_company_id'):
        sub = env['ages.sub.company'].browse(form['sub_company_id'])
        labels.append(('Active Company', sub.display_name))
    if form.get('date_from'):
        labels.append(('Period From', fields.Date.to_string(form['date_from'])))
    if form.get('date_to'):
        labels.append(('Period To', fields.Date.to_string(form['date_to'])))
    if form.get('analytic_account_id'):
        aa = env['account.analytic.account'].browse(form['analytic_account_id'])
        from .report_display import clip_project_name
        labels.append(('Project / Analytic Account', clip_project_name(aa.name or aa.display_name)))
    if form.get('account_id'):
        account = env['account.account'].browse(form['account_id'])
        labels.append(('Chart of Account', f'{account.code} — {account.name}'))
    if form.get('partner_id'):
        partner = env['res.partner'].browse(form['partner_id'])
        labels.append(('Partner / Vendor', partner.display_name))

    target_move = form.get('target_move') or 'posted'
    target_labels = {
        'draft': 'Draft',
        'posted': 'Posted',
        'all': 'All',
    }
    labels.append(('Entries', target_labels.get(target_move, target_move)))

    if form.get('hide_account_payable', True):
        labels.append((
            '211000 Account Payable',
            'Hidden (unchecked to show)',
        ))
    if form.get('hide_cost_of_revenue', True):
        labels.append((
            'Cost of Revenue',
            'Hidden (unchecked to show)',
        ))
    if form.get('hide_bank', True):
        labels.append((
            'Bank / Cash',
            'Hidden (unchecked to show)',
        ))
    if not labels:
        labels.append(('Filters', 'All records (no filters applied)'))
    return labels


def get_group_by_label(group_by):
    if group_by == 'partner_id':
        return 'Partner / Vendor'
    return 'Project / Analytic Account'


def compute_running_balances(lines):
    """Cumulative balance within a group (resets per section)."""
    running = 0.0
    balances = {}
    for line in lines:
        running += line.balance
        balances[line.id] = running
    return balances


def compute_group_running_balances(grouped_data):
    """Return {line_id: running_balance} for all lines, per group."""
    running_balances = {}
    for lines in grouped_data.values():
        running_balances.update(compute_running_balances(lines))
    return running_balances


def compute_grand_totals(grouped_data):
    credit = debit = balance = 0.0
    for lines in grouped_data.values():
        for line in lines:
            credit += line.credit
            debit += line.debit
            balance += line.balance
    return {'credit': credit, 'debit': debit, 'balance': balance}

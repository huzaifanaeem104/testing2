# -*- coding: utf-8 -*-

from odoo.osv import expression


def _int_ids(values):
    ids = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number:
            ids.append(number)
    return list(dict.fromkeys(ids))


def journal_liquidity_account_ids(journals):
    """Default / payment / suspense accounts that belong to the cashbook."""
    account_ids = []
    for fname in (
        'default_account_id',
        'suspense_account_id',
        'profit_account_id',
        'loss_account_id',
    ):
        if fname in journals._fields:
            account_ids.extend(journals.mapped(fname).ids)
    for fname in (
        'inbound_payment_method_line_ids',
        'outbound_payment_method_line_ids',
    ):
        if fname not in journals._fields:
            continue
        methods = journals.mapped(fname)
        if 'payment_account_id' in methods._fields:
            account_ids.extend(methods.mapped('payment_account_id').ids)
    return list(dict.fromkeys(account_id for account_id in account_ids if account_id))


def journal_reach_domain(env, journal_ids):
    """Moves posted in the journal, or lines hitting that journal's cash/bank account.

    Internal transfers are posted on the source journal while the destination
    cashbook only appears as the line account.
    """
    journal_ids = _int_ids(journal_ids)
    if not journal_ids:
        return []
    journals = env['account.journal'].browse(journal_ids).exists()
    domains = [[('journal_id', 'in', journal_ids)]]
    account_ids = journal_liquidity_account_ids(journals)
    if account_ids:
        domains.append([('account_id', 'in', account_ids)])
    return expression.OR(domains) if len(domains) > 1 else domains[0]


def analytic_reach_domain(env, analytic_ids):
    """Match analytic on the line, the move header, the project, or analytic lines."""
    analytic_ids = _int_ids(analytic_ids)
    if not analytic_ids:
        return []
    domains = [[('analytic_distribution', 'in', analytic_ids)]]
    for analytic_id in analytic_ids:
        domains.append([('analytic_distribution', 'ilike', f'"{analytic_id}"')])
    Move = env['account.move']
    if 'ages_analytic_account_id' in Move._fields:
        domains.append([('move_id.ages_analytic_account_id', 'in', analytic_ids)])
    if 'ages_project_id' in Move._fields:
        domains.append([('move_id.ages_project_id.account_id', 'in', analytic_ids)])
    Line = env['account.move.line']
    if 'ages_analytic_account_id' in Line._fields:
        domains.append([('ages_analytic_account_id', 'in', analytic_ids)])
    if 'ages_project_id' in Line._fields:
        domains.append([('ages_project_id.account_id', 'in', analytic_ids)])
    if 'analytic_line_ids' in Line._fields:
        AnalyticLine = env['account.analytic.line']
        if 'auto_account_id' in AnalyticLine._fields:
            domains.append([('analytic_line_ids.auto_account_id', 'in', analytic_ids)])
        elif 'account_id' in AnalyticLine._fields:
            domains.append([('analytic_line_ids.account_id', 'in', analytic_ids)])
    return expression.OR(domains)


def partner_project_analytic_ids(env, partner_ids):
    """Analytic accounts that belong to the partner via project or analytic.partner_id."""
    partner_ids = _int_ids(partner_ids)
    analytic_ids = []
    if not partner_ids:
        return analytic_ids
    Project = env['project.project']
    if 'partner_id' in Project._fields:
        projects = Project.search([('partner_id', 'in', partner_ids)])
        analytic_ids.extend(projects.mapped('account_id').ids)
    Analytic = env['account.analytic.account']
    if 'partner_id' in Analytic._fields:
        analytic_ids.extend(Analytic.search([('partner_id', 'in', partner_ids)]).ids)
    return list(dict.fromkeys(analytic_id for analytic_id in analytic_ids if analytic_id))


def partner_reach_domain(env, partner_ids):
    """Partner on the line, or project/analytic tagged for that client.

    Internal transfers stamp the project/analytic and leave partner_id empty.
    """
    partner_ids = _int_ids(partner_ids)
    if not partner_ids:
        return []
    domains = [[('partner_id', 'in', partner_ids)]]
    Project = env['project.project']
    if 'partner_id' in Project._fields:
        projects = Project.search([('partner_id', 'in', partner_ids)])
        if projects:
            Move = env['account.move']
            if 'ages_project_id' in Move._fields:
                domains.append([('move_id.ages_project_id', 'in', projects.ids)])
            if 'ages_project_id' in env['account.move.line']._fields:
                domains.append([('ages_project_id', 'in', projects.ids)])
    analytic_ids = partner_project_analytic_ids(env, partner_ids)
    if analytic_ids:
        domains.append(analytic_reach_domain(env, analytic_ids))
    return expression.OR(domains)


def and_domains(*domains):
    parts = [domain for domain in domains if domain]
    if not parts:
        return []
    if len(parts) == 1:
        return list(parts[0])
    return expression.AND(parts)


def exclude_ages_srb_wht_refund_domain():
    """Hide temporary AGES-SRB-WHT credit notes from partner/general ledgers.

    Those out_refunds (RINV / AGES-SRB-WHT:%) were a one-off 20/80 sales-tax
    fix; running-bill invoices now book SRB credit 100% / debit WTH share, so
    the notes must not appear on ledgers.
    """
    return [
        '|',
        ('move_id.ref', '=', False),
        ('move_id.ref', 'not like', 'AGES-SRB-WHT:%'),
    ]

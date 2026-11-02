# -*- coding: utf-8 -*-

from odoo import fields

from odoo.addons.ages_custom_reports.report.report_branding import get_ages_branding_values


def analytic_label(env, distribution):
    if not distribution:
        return ''
    ids = []
    for key in distribution:
        try:
            ids.append(int(key))
        except (TypeError, ValueError):
            continue
    if not ids:
        return ''
    return ', '.join(env['account.analytic.account'].browse(ids).mapped('display_name'))


def company_from_project(project, env):
    if not project:
        return env.company
    if project.company_id:
        return project.company_id
    if 'ages_sub_company_id' in project._fields and project.ages_sub_company_id.company_id:
        return project.ages_sub_company_id.company_id
    return env.company


def _project_from_record(record):
    for fname in ('ages_project_id', 'project_id', 'construction_project_id'):
        if fname in record._fields and record[fname]:
            return record[fname]
    return record.env['project.project']


def first_project(record):
    project = _project_from_record(record)
    if project:
        return project
    for line_fname in ('order_line', 'move_ids', 'move_ids_without_package', 'line_ids'):
        if line_fname not in record._fields:
            continue
        lines = record[line_fname]
        if not lines:
            continue
        for fname in ('ages_project_id', 'project_id', 'construction_project_id'):
            if fname in lines._fields:
                projects = lines.mapped(fname)
                if projects:
                    return projects[0]
    return record.env['project.project']


def resolve_report_company(env, records):
    for record in records:
        project = first_project(record)
        if project:
            return company_from_project(project, env)
        if 'company_id' in record._fields and record.company_id:
            return record.company_id
    return env.company


def branding_for_company(company):
    values = get_ages_branding_values()
    if company:
        values['ages_company_name'] = company.name or values['ages_company_name']
        parts = [
            company.street,
            company.street2,
            company.city,
            company.state_id.name if company.state_id else False,
            company.country_id.name if company.country_id else False,
        ]
        address = ', '.join(part for part in parts if part)
        if address:
            values['ages_company_address'] = address
        if company.email:
            values['ages_company_email'] = company.email
    return values


def accounting_lines(lines):
    return lines.filtered(lambda line: line.display_type not in ('line_section', 'line_note'))


def move_line_rows(env, lines):
    rows = []
    for line in accounting_lines(lines):
        rows.append({
            'date': line.date,
            'move_name': line.move_id.name or '',
            'partner': line.partner_id.display_name or '',
            'label': line.name or '',
            'account': line.account_id.display_name or '',
            'analytic': analytic_label(env, line.analytic_distribution),
            'debit': line.debit,
            'credit': line.credit,
        })
    return rows


def selection_label(record, field_name):
    field = record._fields.get(field_name)
    if not field:
        return ''
    return dict(field._description_selection(record.env)).get(record[field_name], record[field_name] or '')


def report_base_values(env, docids, doc_model, records, title, subtitle=''):
    company = resolve_report_company(env, records)
    return {
        'doc_ids': docids,
        'doc_model': doc_model,
        'docs': records,
        'company': company,
        'currency': company.currency_id,
        'report_date': fields.Date.context_today(env.user),
        'report_title': title,
        'report_subtitle': subtitle,
        **branding_for_company(company),
    }

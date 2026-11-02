# -*- coding: utf-8 -*-

import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..report.opal_xlsx_io import (
    SHEET_CLIENT_ACCOUNT,
    SHEET_CLIENT_PROJECT,
    SHEET_CLIENT_TOTAL,
    SHEET_PROJECT_CLIENT_TOTAL,
    SHEET_PROJECT_TOTAL,
    SHEET_VENDOR_ACCOUNT,
    SHEET_VENDOR_PROJECT,
    SHEET_VENDOR_TOTAL,
    assert_totals_match,
    parse_workbook,
    rows_from_project_total,
    rows_from_vendor_account,
    rows_from_vendor_project,
    rows_from_vendor_total,
)


class OpalVendorBalanceImport(models.Model):
    _name = 'opal.vendor.balance.import'
    _description = 'OPAL vendor balance import'
    _order = 'imported_at desc, id desc'

    name = fields.Char(required=True)
    data_file = fields.Binary(attachment=True)
    data_filename = fields.Char()
    imported_by = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        readonly=True,
    )
    imported_at = fields.Datetime(readonly=True)
    line_count = fields.Integer(readonly=True)
    vendor_count = fields.Integer(readonly=True)
    client_count = fields.Integer(readonly=True)
    project_count = fields.Integer(readonly=True)
    account_line_count = fields.Integer(readonly=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Imported')],
        default='draft',
        required=True,
    )
    note = fields.Text()

    @api.model
    def _default_name(self):
        return _('OPAL import %s') % fields.Datetime.now().strftime('%Y-%m-%d %H:%M')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('name', self._default_name())
        return super().create(vals_list)

    def _process_import(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only accounting managers can import OPAL reference data.'))
        data = self.data_file
        if isinstance(data, str):
            data = base64.b64decode(data)
        elif isinstance(data, (bytes, bytearray)):
            try:
                data = base64.b64decode(data)
            except Exception:
                data = bytes(data)
        sheets = parse_workbook(data)
        client_balance = (lambda debit, credit: debit - credit)

        vendor_rows = rows_from_vendor_project(sheets[SHEET_VENDOR_PROJECT])
        if not vendor_rows:
            raise UserError(_('Vendor_by_Project has no vendor rows.'))
        vendor_accounts = rows_from_vendor_account(sheets.get(SHEET_VENDOR_ACCOUNT) or [])
        vendor_totals = rows_from_vendor_total(sheets.get(SHEET_VENDOR_TOTAL) or [])
        project_totals = rows_from_project_total(sheets.get(SHEET_PROJECT_TOTAL) or [])
        if vendor_totals or project_totals:
            assert_totals_match(vendor_rows, vendor_totals, project_totals)

        client_rows = rows_from_vendor_project(
            sheets[SHEET_CLIENT_PROJECT], balance_fn=client_balance,
        )
        if not client_rows:
            raise UserError(_(
                'Client_by_Project has no client rows. '
                'Upload OPAL Vendor Balance by Project.xlsx (combined vendors + clients).'
            ))
        client_accounts = rows_from_vendor_account(
            sheets.get(SHEET_CLIENT_ACCOUNT) or [], balance_fn=client_balance,
        )
        client_totals = rows_from_vendor_total(sheets.get(SHEET_CLIENT_TOTAL) or [])
        client_project_totals = rows_from_project_total(
            sheets.get(SHEET_PROJECT_CLIENT_TOTAL) or []
        )
        if client_totals or client_project_totals:
            assert_totals_match(client_rows, client_totals, client_project_totals)

        self._replace_all_rows(vendor_rows, vendor_accounts, client_rows, client_accounts)
        self._suggest_maps(vendor_rows)
        self._suggest_maps(client_rows)

        previous_done = self.search([('state', '=', 'done'), ('id', '!=', self.id)])
        if previous_done:
            previous_done.write({'state': 'draft', 'note': _('Replaced by %s') % self.display_name})

        all_rows = vendor_rows + client_rows
        self.write({
            'state': 'done',
            'imported_at': fields.Datetime.now(),
            'imported_by': self.env.user.id,
            'line_count': len(all_rows),
            'vendor_count': len({row['vendor_name'] for row in vendor_rows}),
            'client_count': len({row['vendor_name'] for row in client_rows}),
            'project_count': len({row['project_code'] for row in all_rows}),
            'account_line_count': len(vendor_accounts) + len(client_accounts),
            'note': _(
                'Replaced OPAL data with %s vendors (%s rows) and %s clients (%s rows).'
            ) % (
                len({row['vendor_name'] for row in vendor_rows}),
                len(vendor_rows),
                len({row['vendor_name'] for row in client_rows}),
                len(client_rows),
            ),
        })
        return True

    def _replace_all_rows(self, vendor_rows, vendor_accounts, client_rows, client_accounts):
        Line = self.env['opal.vendor.project']
        Account = self.env['opal.vendor.project.account']
        Account.search([]).unlink()
        Line.search([]).unlink()
        self.env.flush_all()
        self._create_party_rows('vendor', vendor_rows, vendor_accounts)
        self._create_party_rows('client', client_rows, client_accounts)

    def _create_party_rows(self, party_type, project_rows, account_rows):
        Line = self.env['opal.vendor.project']
        Account = self.env['opal.vendor.project.account']
        currency = self.env.company.currency_id
        vendor_maps = {
            rec.vendor_name: rec.partner_id.id
            for rec in self.env['opal.vendor.map'].search([])
            if rec.partner_id
        }
        project_maps = {
            rec.project_code: rec.project_id.id
            for rec in self.env['opal.project.map'].search([])
            if rec.project_id
        }
        line_vals = []
        for row in project_rows:
            line_vals.append({
                'vendor_name': row['vendor_name'],
                'project_code': row['project_code'],
                'project_name': row['project_name'],
                'debit': row['debit'],
                'credit': row['credit'],
                'balance': row['balance'],
                'party_type': party_type,
                'currency_id': currency.id,
                'partner_id': vendor_maps.get(row['vendor_name'], False),
                'project_id': project_maps.get(row['project_code'], False),
                'import_id': self.id,
            })
        self._create_in_batches(Line, line_vals)
        account_vals = []
        for row in account_rows:
            account_vals.append({
                'vendor_name': row['vendor_name'],
                'project_code': row['project_code'],
                'project_name': row['project_name'],
                'category': row['category'],
                'account_name': row['account_name'],
                'debit': row['debit'],
                'credit': row['credit'],
                'balance': row['balance'],
                'party_type': party_type,
                'currency_id': currency.id,
                'partner_id': vendor_maps.get(row['vendor_name'], False),
                'project_id': project_maps.get(row['project_code'], False),
                'import_id': self.id,
            })
        self._create_in_batches(Account, account_vals)

    def _create_in_batches(self, model, values, batch=200):
        if not values:
            return model.browse()
        records = model.browse()
        for start in range(0, len(values), batch):
            records |= model.create(values[start:start + batch])
        return records

    def _suggest_maps(self, project_rows):
        Partner = self.env['res.partner']
        Project = self.env['project.project']
        VendorMap = self.env['opal.vendor.map']
        ProjectMap = self.env['opal.project.map']
        existing_vendors = {rec.vendor_name for rec in VendorMap.search([])}
        for vendor in {row['vendor_name'] for row in project_rows}:
            if vendor in existing_vendors:
                continue
            matches = Partner.search([
                '|',
                ('name', '=ilike', vendor),
                ('display_name', '=ilike', vendor),
            ])
            if len(matches) == 1:
                VendorMap.create({
                    'vendor_name': vendor,
                    'partner_id': matches.id,
                    'notes': _('Auto-mapped on import'),
                })
                existing_vendors.add(vendor)
            elif vendor not in existing_vendors:
                VendorMap.create({'vendor_name': vendor})
                existing_vendors.add(vendor)
        names_by_code = {}
        for row in project_rows:
            names_by_code.setdefault(row['project_code'], row.get('project_name') or '')
        for code, project_name in names_by_code.items():
            existing = ProjectMap.search([('project_code', '=', code)], limit=1)
            if existing:
                if project_name and not existing.project_name:
                    existing.project_name = project_name
                continue
            domain = [('name', 'ilike', code)]
            if project_name:
                domain = ['|', ('name', 'ilike', code), ('name', 'ilike', project_name)]
            matches = Project.search(domain)
            vals = {'project_code': code, 'project_name': project_name}
            if len(matches) == 1:
                vals['project_id'] = matches.id
            ProjectMap.create(vals)

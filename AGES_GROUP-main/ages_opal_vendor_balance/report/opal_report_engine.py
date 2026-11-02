# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields

from odoo.addons.ages_custom_reports.report.report_display import clip_project_name


SOURCE_LABELS = {
    'odoo_overall': 'Odoo Overall',
    'opal_overall': 'OPAL Overall',
    'opal_project': 'OPAL Project',
    'opal_account': 'OPAL Account',
    'opal_vendor_total': 'OPAL Overall',
    'opal_project_total': 'OPAL Project',
}

TAB_COLUMNS = {
    'vendor_project': [
        {'id': 'source', 'label': 'Source'},
        {'id': 'vendor', 'label': 'Vendor / Client'},
        {'id': 'project_code', 'label': 'Project Code'},
        {'id': 'project_name', 'label': 'Project Name'},
        {'id': 'debit', 'label': 'Debit', 'type': 'monetary'},
        {'id': 'credit', 'label': 'Credit', 'type': 'monetary'},
        {'id': 'balance', 'label': 'Balance', 'type': 'monetary'},
        {'id': 'variance', 'label': 'Variance', 'type': 'monetary'},
    ],
    'vendor_account': [
        {'id': 'vendor', 'label': 'Vendor / Client'},
        {'id': 'project_code', 'label': 'Project Code'},
        {'id': 'project_name', 'label': 'Project Name'},
        {'id': 'category', 'label': 'Category'},
        {'id': 'account_name', 'label': 'Account Name'},
        {'id': 'debit', 'label': 'Debit', 'type': 'monetary'},
        {'id': 'credit', 'label': 'Credit', 'type': 'monetary'},
        {'id': 'balance', 'label': 'Balance', 'type': 'monetary'},
    ],
    'vendor_total': [
        {'id': 'source', 'label': 'Source'},
        {'id': 'vendor', 'label': 'Vendor / Client'},
        {'id': 'projects', 'label': 'Projects'},
        {'id': 'debit', 'label': 'Debit', 'type': 'monetary'},
        {'id': 'credit', 'label': 'Credit', 'type': 'monetary'},
        {'id': 'balance', 'label': 'Balance', 'type': 'monetary'},
        {'id': 'variance', 'label': 'Variance', 'type': 'monetary'},
    ],
    'project_total': [
        {'id': 'project_code', 'label': 'Project Code'},
        {'id': 'project_name', 'label': 'Project Name'},
        {'id': 'vendors', 'label': 'Vendors'},
        {'id': 'debit', 'label': 'Debit', 'type': 'monetary'},
        {'id': 'credit', 'label': 'Credit', 'type': 'monetary'},
        {'id': 'balance', 'label': 'Balance', 'type': 'monetary'},
    ],
}

_ZERO = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
_PROJECT_FIELDS = [
    'vendor_name', 'project_code', 'project_name',
    'debit', 'credit', 'balance', 'partner_id', 'project_id', 'party_type',
]
_ACCOUNT_FIELDS = _PROJECT_FIELDS + ['category', 'account_name']


def _many2one_id(value):
    return value[0] if value else False


def _many2one_name(value):
    return value[1] if value else ''


class OpalVendorBalanceEngine:
    def __init__(self, env, options=None):
        self.env = env
        self.options = options or {}
        self.company = env.company
        self.currency = self.company.currency_id
        self.company_ids = tuple(env.companies.ids or [self.company.id])
        self.as_of = fields.Date.to_date(
            self.options.get('as_of') or fields.Date.context_today(env.user)
        )
        self.tab = self.options.get('tab') or 'vendor_project'
        if self.tab not in TAB_COLUMNS:
            self.tab = 'vendor_project'
        self.hidden_column_ids = {
            str(item) for item in (self.options.get('hidden_column_ids') or []) if item
        }
        self.full_dataset = bool(self.options.get('full_dataset'))
        self.line_search = '' if self.full_dataset else (self.options.get('line_search') or '').strip().lower()
        self.show_zero_lines = True if self.full_dataset else self.options.get('show_zero_lines', True)
        self.show_odoo_overall = bool(self.options.get('show_odoo_overall'))
        self.show_unmapped_only = False if self.full_dataset else bool(self.options.get('show_unmapped_only'))
        self._payable_cache = {}
        self._receivable_cache = {}

    def visible_columns(self, columns=None):
        columns = list(columns or TAB_COLUMNS[self.tab])
        visible = [column for column in columns if column['id'] not in self.hidden_column_ids]
        return visible or columns

    def get_report_data(self):
        last_import = self.env['opal.vendor.balance.import'].search(
            [('state', '=', 'done')], limit=1
        )
        builders = {
            'vendor_project': self._tab_vendor_project,
            'vendor_account': self._tab_vendor_account,
            'vendor_total': self._tab_vendor_total,
            'project_total': self._tab_project_total,
        }
        lines = builders[self.tab]()
        imported_at = False
        imported_by = ''
        if last_import and last_import.imported_at:
            imported_at = fields.Datetime.to_string(last_import.imported_at)
            imported_by = last_import.imported_by.display_name if last_import.imported_by else ''
        return {
            'tab': self.tab,
            'columns': TAB_COLUMNS[self.tab],
            'lines': lines,
            'totals': self._totals(lines),
            'warnings': [],
            'currency_id': self.currency.id,
            'imported_at': imported_at,
            'imported_by': imported_by,
            'unmapped_vendor_count': 0,
            'has_data': bool(last_import),
            'as_of': fields.Date.to_string(self.as_of),
            'account_index': self._account_index() if self.full_dataset else {},
            **(self.get_filter_options() if self.full_dataset else {}),
        }

    def get_filter_options(self):
        cr = self.env.cr
        cr.execute("""
            SELECT DISTINCT vendor_name
              FROM opal_vendor_project
             WHERE vendor_name IS NOT NULL
             ORDER BY vendor_name
        """)
        vendors = [row[0] for row in cr.fetchall()]
        cr.execute("""
            SELECT project_code, MAX(COALESCE(project_name, ''))
              FROM opal_vendor_project
             WHERE project_code IS NOT NULL
             GROUP BY project_code
             ORDER BY project_code
        """)
        projects = [{'code': code, 'name': name or ''} for code, name in cr.fetchall()]
        cr.execute("""
            SELECT DISTINCT account_name
              FROM opal_vendor_project_account
             WHERE account_name IS NOT NULL
               AND account_name != ''
             ORDER BY account_name
        """)
        return {
            'vendor_options': vendors,
            'project_options': projects,
            'account_options': [row[0] for row in cr.fetchall()],
        }

    def _selected_vendor_names(self):
        if self.full_dataset:
            return set()
        names = {name for name in (self.options.get('vendor_names') or []) if name}
        partner_ids = [pid for pid in (self.options.get('partner_ids') or []) if pid]
        if partner_ids:
            self.env.cr.execute(
                "SELECT vendor_name FROM opal_vendor_map WHERE partner_id IN %s",
                [tuple(partner_ids)],
            )
            names.update(row[0] for row in self.env.cr.fetchall() if row[0])
        return names

    def _selected_project_codes(self):
        if self.full_dataset:
            return set()
        codes = {code for code in (self.options.get('project_codes') or []) if code}
        project_ids = [pid for pid in (self.options.get('project_ids') or []) if pid]
        if project_ids:
            self.env.cr.execute(
                "SELECT project_code FROM opal_project_map WHERE project_id IN %s",
                [tuple(project_ids)],
            )
            codes.update(row[0] for row in self.env.cr.fetchall() if row[0])
            self.env.cr.execute(
                "SELECT DISTINCT project_code FROM opal_vendor_project WHERE project_id IN %s",
                [tuple(project_ids)],
            )
            codes.update(row[0] for row in self.env.cr.fetchall() if row[0])
        return codes

    def _selected_account_names(self):
        if self.full_dataset:
            return set()
        return {name for name in (self.options.get('account_names') or []) if name}

    def _vendor_project_pairs_for_accounts(self):
        accounts = self._selected_account_names()
        if not accounts:
            return None
        self.env.cr.execute(
            """
            SELECT DISTINCT vendor_name, project_code
              FROM opal_vendor_project_account
             WHERE account_name IN %s
            """,
            [tuple(accounts)],
        )
        return set(self.env.cr.fetchall())

    def _account_index(self):
        self.env.cr.execute("""
            SELECT vendor_name, project_code, account_name
              FROM opal_vendor_project_account
             WHERE COALESCE(account_name, '') != ''
        """)
        index = defaultdict(list)
        for vendor, code, name in self.env.cr.fetchall():
            index['%s\t%s' % (vendor, code)].append(name)
        return dict(index)

    def _project_domain(self):
        domain = []
        vendors = self._selected_vendor_names()
        if vendors:
            domain.append(('vendor_name', 'in', list(vendors)))
        codes = self._selected_project_codes()
        if codes:
            domain.append(('project_code', 'in', list(codes)))
        if self.show_unmapped_only:
            domain.append(('partner_id', '=', False))
        return domain

    def _read_project_rows(self):
        rows = self.env['opal.vendor.project'].search_read(
            self._project_domain(),
            _PROJECT_FIELDS,
            order='vendor_name, project_code',
        )
        pairs = self._vendor_project_pairs_for_accounts()
        if pairs is not None:
            rows = [
                row for row in rows
                if (row['vendor_name'], row['project_code']) in pairs
            ]
        if not self.show_zero_lines:
            rows = [row for row in rows if row['balance']]
        return rows

    def _search_hit(self, *parts):
        if not self.line_search:
            return True
        blob = ' '.join(str(part or '') for part in parts).lower()
        return self.line_search in blob

    def _load_partner_balances(self, partner_ids, account_type, cache, balance_fn):
        partner_ids = {int(pid) for pid in partner_ids if pid}
        missing = [pid for pid in partner_ids if pid not in cache]
        if not missing:
            return
        partners = self.env['res.partner'].browse(missing).exists()
        commercial_of = {}
        commercial_ids = set()
        for partner in partners:
            commercial_id = partner.commercial_partner_id.id
            commercial_of[partner.id] = commercial_id
            commercial_ids.add(commercial_id)
        for partner_id in missing:
            if partner_id not in commercial_of:
                commercial_of[partner_id] = partner_id
                commercial_ids.add(partner_id)
        totals = defaultdict(lambda: {'debit': 0.0, 'credit': 0.0})
        if commercial_ids:
            query = """
                SELECT COALESCE(p.commercial_partner_id, p.id),
                       SUM(l.debit),
                       SUM(l.credit)
                  FROM account_move_line l
                  JOIN account_account a ON a.id = l.account_id
                  JOIN res_partner p ON p.id = l.partner_id
                 WHERE l.parent_state = 'posted'
                   AND a.account_type = %s
                   AND l.company_id IN %s
                   AND l.date <= %s
                   AND COALESCE(p.commercial_partner_id, p.id) IN %s
            """
            params = [account_type, self.company_ids, self.as_of, tuple(commercial_ids)]
            sub_ids = [sid for sid in (self.options.get('sub_company_ids') or []) if sid]
            if sub_ids and 'ages_sub_company_id' in self.env['account.move.line']._fields:
                query += " AND l.ages_sub_company_id IN %s"
                params.append(tuple(sub_ids))
            query += " GROUP BY 1"
            self.env.cr.execute(query, params)
            for commercial_id, debit, credit in self.env.cr.fetchall():
                totals[commercial_id] = {
                    'debit': debit or 0.0,
                    'credit': credit or 0.0,
                }
        for commercial_id in commercial_ids:
            amount = totals.get(commercial_id, {'debit': 0.0, 'credit': 0.0})
            cache[commercial_id] = {
                'debit': amount['debit'],
                'credit': amount['credit'],
                'balance': balance_fn(amount['debit'], amount['credit']),
            }
        for partner_id, commercial_id in commercial_of.items():
            cache[partner_id] = cache[commercial_id]

    def _load_payables(self, partner_ids):
        self._load_partner_balances(
            partner_ids, 'liability_payable', self._payable_cache,
            lambda debit, credit: credit - debit,
        )

    def _load_receivables(self, partner_ids):
        self._load_partner_balances(
            partner_ids, 'asset_receivable', self._receivable_cache,
            lambda debit, credit: debit - credit,
        )

    def _odoo_payable(self, partner_id):
        if not partner_id:
            return dict(_ZERO)
        if partner_id not in self._payable_cache:
            self._load_payables([partner_id])
        return self._payable_cache.get(partner_id) or dict(_ZERO)

    def _odoo_receivable(self, partner_id):
        if not partner_id:
            return dict(_ZERO)
        if partner_id not in self._receivable_cache:
            self._load_receivables([partner_id])
        return self._receivable_cache.get(partner_id) or dict(_ZERO)

    def _blank_line(self, **values):
        source = values.get('source') or ''
        return {
            'id': values.get('id') or 'row',
            'source': source,
            'source_label': SOURCE_LABELS.get(source, source),
            'vendor': values.get('vendor') or '',
            'partner_id': values.get('partner_id') or False,
            'project_code': values.get('project_code') or '',
            'project_name': clip_project_name(values.get('project_name') or ''),
            'project_id': values.get('project_id') or False,
            'category': values.get('category') or '',
            'account_name': values.get('account_name') or '',
            'projects': values.get('projects', False),
            'vendors': values.get('vendors', False),
            'debit': values.get('debit', 0.0) or 0.0,
            'credit': values.get('credit', 0.0) or 0.0,
            'balance': values.get('balance', 0.0) or 0.0,
            'variance': values.get('variance', False),
            'mapped': values.get('mapped', True),
            'party_type': values.get('party_type') or 'vendor',
            'line_type': values.get('line_type') or source,
        }

    def _tab_vendor_project(self):
        rows = self._read_project_rows()
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row.get('party_type') or 'vendor', row['vendor_name'])].append(row)
        self._load_payables(
            _many2one_id(row['partner_id'])
            for row in rows if (row.get('party_type') or 'vendor') != 'client'
        )
        self._load_receivables(
            _many2one_id(row['partner_id'])
            for row in rows if row.get('party_type') == 'client'
        )
        lines = []
        for party_type, vendor in sorted(grouped, key=lambda key: key[1].lower()):
            vendor_rows = grouped[(party_type, vendor)]
            if self.line_search:
                matching = [
                    row for row in vendor_rows
                    if self._search_hit(
                        vendor,
                        row['project_code'],
                        row['project_name'],
                        _many2one_name(row['partner_id']),
                    )
                ]
                if not matching:
                    continue
                if not self._search_hit(vendor):
                    vendor_rows = matching
            partner_id = _many2one_id(vendor_rows[0]['partner_id'])
            mapped = bool(partner_id)
            is_client = party_type == 'client'
            odoo = (
                self._odoo_receivable(partner_id) if is_client else self._odoo_payable(partner_id)
            ) if mapped else dict(_ZERO)
            opal_debit = sum(row['debit'] or 0.0 for row in vendor_rows)
            opal_credit = sum(row['credit'] or 0.0 for row in vendor_rows)
            opal_balance = sum(row['balance'] or 0.0 for row in vendor_rows)
            lines.append(self._blank_line(
                id='odoo:%s:%s' % (party_type, vendor),
                source='odoo_overall',
                vendor=vendor,
                partner_id=partner_id,
                project_code='—',
                project_name='—' if mapped else 'Not mapped',
                debit=odoo['debit'],
                credit=odoo['credit'],
                balance=odoo['balance'],
                variance=odoo['balance'] - opal_balance,
                mapped=mapped,
                party_type=party_type,
            ))
            lines.append(self._blank_line(
                id='opal-overall:%s:%s' % (party_type, vendor),
                source='opal_overall',
                vendor=vendor,
                partner_id=partner_id,
                project_code='—',
                project_name='All projects',
                debit=opal_debit,
                credit=opal_credit,
                balance=opal_balance,
                mapped=mapped,
                party_type=party_type,
            ))
            for row in vendor_rows:
                lines.append(self._blank_line(
                    id='opal-project:%s:%s:%s' % (
                        party_type, vendor, row['project_code'],
                    ),
                    source='opal_project',
                    vendor=vendor,
                    partner_id=partner_id,
                    project_code=row['project_code'],
                    project_name=row['project_name'],
                    project_id=_many2one_id(row['project_id']),
                    debit=row['debit'],
                    credit=row['credit'],
                    balance=row['balance'],
                    mapped=mapped,
                    party_type=party_type,
                ))
        return lines

    def _tab_vendor_account(self):
        domain = self._project_domain()
        accounts = self._selected_account_names()
        if accounts:
            domain.append(('account_name', 'in', list(accounts)))
        rows = self.env['opal.vendor.project.account'].search_read(
            domain,
            _ACCOUNT_FIELDS,
            order='vendor_name, project_code, account_name',
        )
        if not self.show_zero_lines:
            rows = [row for row in rows if row['balance']]
        lines = []
        for index, row in enumerate(rows):
            if not self._search_hit(
                row['vendor_name'], row['project_code'], row['project_name'],
                row.get('category'), row.get('account_name'),
            ):
                continue
            lines.append(self._blank_line(
                id='opal-account:%s:%s:%s:%s:%s' % (
                    row.get('party_type') or 'vendor',
                    row['vendor_name'], row['project_code'], row.get('account_name') or '', index,
                ),
                source='opal_account',
                vendor=row['vendor_name'],
                partner_id=_many2one_id(row['partner_id']),
                project_code=row['project_code'],
                project_name=row['project_name'],
                project_id=_many2one_id(row['project_id']),
                category=row.get('category'),
                account_name=row.get('account_name'),
                debit=row['debit'],
                credit=row['credit'],
                balance=row['balance'],
                mapped=bool(_many2one_id(row['partner_id'])),
                party_type=row.get('party_type') or 'vendor',
            ))
        return lines

    def _tab_vendor_total(self):
        rows = self._read_project_rows()
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row.get('party_type') or 'vendor', row['vendor_name'])].append(row)
        self._load_payables(
            _many2one_id(row['partner_id'])
            for row in rows if (row.get('party_type') or 'vendor') != 'client'
        )
        self._load_receivables(
            _many2one_id(row['partner_id'])
            for row in rows if row.get('party_type') == 'client'
        )
        searched = bool(self.line_search or self._selected_vendor_names())
        include_odoo = self.full_dataset or searched or self.show_odoo_overall
        lines = []
        for party_type, vendor in sorted(grouped, key=lambda key: key[1].lower()):
            vendor_rows = grouped[(party_type, vendor)]
            if self.line_search and not self._search_hit(vendor):
                if not any(
                    self._search_hit(vendor, row['project_code'], row['project_name'])
                    for row in vendor_rows
                ):
                    continue
            partner_id = _many2one_id(vendor_rows[0]['partner_id'])
            mapped = bool(partner_id)
            is_client = party_type == 'client'
            opal_debit = sum(row['debit'] or 0.0 for row in vendor_rows)
            opal_credit = sum(row['credit'] or 0.0 for row in vendor_rows)
            opal_balance = sum(row['balance'] or 0.0 for row in vendor_rows)
            if include_odoo:
                odoo = dict(_ZERO)
                if mapped:
                    odoo = (
                        self._odoo_receivable(partner_id)
                        if is_client else self._odoo_payable(partner_id)
                    )
                lines.append(self._blank_line(
                    id='odoo-total:%s:%s' % (party_type, vendor),
                    source='odoo_overall',
                    vendor=vendor,
                    partner_id=partner_id,
                    projects='—',
                    debit=odoo['debit'],
                    credit=odoo['credit'],
                    balance=odoo['balance'],
                    variance=odoo['balance'] - opal_balance,
                    mapped=mapped,
                    party_type=party_type,
                ))
            lines.append(self._blank_line(
                id='opal-total:%s:%s' % (party_type, vendor),
                source='opal_vendor_total',
                vendor=vendor,
                partner_id=partner_id,
                projects=len({row['project_code'] for row in vendor_rows}),
                debit=opal_debit,
                credit=opal_credit,
                balance=opal_balance,
                mapped=mapped,
                party_type=party_type,
            ))
        return lines

    def _tab_project_total(self):
        rows = self._read_project_rows()
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['project_code']].append(row)
        lines = []
        for code in sorted(grouped):
            project_rows = grouped[code]
            name = next((row['project_name'] for row in project_rows if row['project_name']), '')
            if not self._search_hit(code, name, *(row['vendor_name'] for row in project_rows)):
                continue
            lines.append(self._blank_line(
                id='opal-project-total:%s' % code,
                source='opal_project_total',
                project_code=code,
                project_name=name,
                project_id=next(
                    (_many2one_id(row['project_id']) for row in project_rows if row['project_id']),
                    False,
                ),
                vendors=len({row['vendor_name'] for row in project_rows}),
                debit=sum(row['debit'] or 0.0 for row in project_rows),
                credit=sum(row['credit'] or 0.0 for row in project_rows),
                balance=sum(row['balance'] or 0.0 for row in project_rows),
            ))
        return lines

    def _totals(self, lines):
        kinds = {
            'vendor_project': 'opal_project',
            'vendor_account': 'opal_account',
            'vendor_total': 'opal_vendor_total',
            'project_total': 'opal_project_total',
        }
        kind = kinds[self.tab]
        chosen = [line for line in lines if line.get('source') == kind]
        return {
            'debit': sum(line['debit'] for line in chosen),
            'credit': sum(line['credit'] for line in chosen),
            'balance': sum(line['balance'] for line in chosen),
        }

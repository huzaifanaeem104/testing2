# -*- coding: utf-8 -*-

import re
from collections import defaultdict

from odoo import models
from odoo.addons.ages_custom_reports.report.report_display import clip_project_name

# Odoo analytic / project titles often differ from short OPAL names
# (e.g. "SINDHARI SUGAR MILLS" ↔ OPAL "SINDHRI").
_PROJECT_ALIASES = {
    'sindhri': frozenset({'sindhri', 'sindhari'}),
    'sindhari': frozenset({'sindhri', 'sindhari'}),
    'deharki': frozenset({'deharki', 'daharki'}),
    'daharki': frozenset({'deharki', 'daharki'}),
    'almoiz': frozenset({'almoiz', 'almoiz1', 'al-moiz'}),
    'unicol': frozenset({'unicol'}),
    'bandhi': frozenset({'bandhi', 'bandh'}),
}
_NOISE_RE = re.compile(
    r'\b(sugar|mills?|mill|sm|cement|dairy|farm|client|clients|ltd|limited|'
    r'pvt|private|company|co|the|and|&)\b',
    re.I,
)


class OpalPartnerLedgerHook(models.AbstractModel):
    _name = 'opal.partner.ledger.hook'
    _description = 'OPAL rows for Partner Ledger and General Ledger'

    def _clip(self, name):
        return clip_project_name(name)

    def _coerce_id(self, value):
        if value in (None, False, '', 0, '0'):
            return False
        if isinstance(value, (list, tuple)):
            return self._coerce_id(value[0] if value else False)
        if isinstance(value, dict):
            return self._coerce_id(value.get('id') or value.get('resId'))
        try:
            return int(value)
        except (TypeError, ValueError):
            return False

    def _canonical_key(self, text):
        key = re.sub(r'[^a-z0-9]+', '', (text or '').lower())
        for source, target in (
            ('sindhari', 'sindhri'),
            ('daharki', 'deharki'),
            ('sugarmills', ''),
            ('sugarmill', ''),
        ):
            key = key.replace(source, target)
        return key

    def _project_tokens(self, raw):
        """Normalize a project / analytic title into match tokens."""
        clipped = (self._clip(raw) or '').strip().lower()
        if not clipped:
            return set()
        cleaned = _NOISE_RE.sub(' ', clipped)
        cleaned = re.sub(r'[^a-z0-9]+', ' ', cleaned).strip()
        tokens = {clipped, cleaned} if cleaned else {clipped}
        canonical = self._canonical_key(clipped)
        if canonical:
            tokens.add(canonical)
        for part in cleaned.split():
            if len(part) >= 3:
                tokens.add(part)
                tokens.update(_PROJECT_ALIASES.get(part, ()))
                part_key = self._canonical_key(part)
                if part_key:
                    tokens.add(part_key)
        first = clipped.split()[0] if clipped.split() else ''
        if first and len(first) >= 3:
            tokens.add(first)
            tokens.update(_PROJECT_ALIASES.get(first, ()))
            first_key = self._canonical_key(first)
            if first_key:
                tokens.add(first_key)
        return {t for t in tokens if t}

    def _tokens_match(self, left, right):
        if not left or not right:
            return False
        if left == right or left in right or right in left:
            return True
        left_key = self._canonical_key(left)
        right_key = self._canonical_key(right)
        if left_key and right_key and (
            left_key == right_key or left_key in right_key or right_key in left_key
        ):
            return True
        n = 0
        for a, b in zip(left, right):
            if a != b:
                break
            n += 1
        return n >= 5 and min(len(left), len(right)) >= 5

    def _project_filter(self, options):
        """Return match info when Partner Ledger / GL has a project filter.

        None  → no project selected (show all OPAL rows as before).
        dict  → restrict OPAL rows to the matching project code/name.
        """
        analytic_id = self._coerce_id(options.get('analytic_account_id'))
        if not analytic_id:
            return None
        analytic = self.env['account.analytic.account'].browse(analytic_id).exists()
        if not analytic:
            return {'codes': set(), 'names': set(), 'label': ''}

        codes = set()
        Project = self.env['project.project']
        projects = Project.browse()
        if 'account_id' in Project._fields:
            projects = Project.search([('account_id', '=', analytic.id)])
        if projects:
            self.env.cr.execute(
                """
                SELECT project_code
                  FROM opal_project_map
                 WHERE project_id IN %s
                   AND project_code IS NOT NULL
                """,
                [tuple(projects.ids)],
            )
            codes.update(row[0] for row in self.env.cr.fetchall() if row[0])
            self.env.cr.execute(
                """
                SELECT DISTINCT project_code
                  FROM opal_vendor_project
                 WHERE project_id IN %s
                   AND project_code IS NOT NULL
                """,
                [tuple(projects.ids)],
            )
            codes.update(row[0] for row in self.env.cr.fetchall() if row[0])

        names = set()
        for raw in (
            analytic.name,
            analytic.display_name,
            options.get('analytic_account_name'),
            *(projects.mapped('name') if projects else []),
            *(projects.mapped('display_name') if projects else []),
        ):
            names.update(self._project_tokens(raw))

        # Also find Odoo projects by short name when analytic is not linked.
        if names and 'name' in Project._fields:
            name_domain = []
            for token in names:
                if len(token) < 4 or token.isdigit():
                    continue
                clause = [('name', 'ilike', token)]
                name_domain = clause if not name_domain else ['|'] + clause + name_domain
            if name_domain:
                named_projects = Project.search(name_domain)
                projects = projects | named_projects
                for rec in named_projects:
                    names.update(self._project_tokens(rec.name))
                    names.update(self._project_tokens(rec.display_name))
                if named_projects:
                    self.env.cr.execute(
                        """
                        SELECT project_code
                          FROM opal_project_map
                         WHERE project_id IN %s
                           AND project_code IS NOT NULL
                        """,
                        [tuple(named_projects.ids)],
                    )
                    codes.update(row[0] for row in self.env.cr.fetchall() if row[0])

        # Resolve OPAL codes by fuzzy name when the analytic is not mapped yet
        # (SINDHARI SUGAR MILLS → AG-SO-0017-24 / SINDHRI).
        if names:
            self.env.cr.execute(
                """
                SELECT DISTINCT project_code, project_name
                  FROM opal_vendor_project
                 WHERE project_code IS NOT NULL
                """
            )
            for project_code, project_name in self.env.cr.fetchall():
                if not project_code or project_code in codes:
                    continue
                opal_tokens = self._project_tokens(project_name) | self._project_tokens(project_code)
                if any(
                    self._tokens_match(token, opal)
                    for token in names
                    for opal in opal_tokens
                ):
                    codes.add(project_code)
            for token in names:
                if len(token) < 4 or token.isdigit():
                    continue
                self.env.cr.execute(
                    """
                    SELECT DISTINCT project_code
                      FROM opal_vendor_project
                     WHERE project_code IS NOT NULL
                       AND (
                            project_name ILIKE %s
                         OR project_code ILIKE %s
                       )
                    """,
                    ['%%%s%%' % token, '%%%s%%' % token],
                )
                codes.update(row[0] for row in self.env.cr.fetchall() if row[0])

        return {
            'codes': codes,
            'names': names,
            'label': self._clip(analytic.name or analytic.display_name or '') or 'Project',
        }

    def _row_matches_project(self, row, project_filter):
        if not project_filter:
            return True
        code = row.get('project_code') or ''
        if code and code in project_filter['codes']:
            return True
        opal_tokens = self._project_tokens(row.get('project_name')) | self._project_tokens(code)
        if not opal_tokens:
            return False
        for token in project_filter['names']:
            for opal in opal_tokens:
                if self._tokens_match(token, opal):
                    return True
        return False

    def _vendor_names_for_partner(self, partner):
        """Resolve OPAL vendor names from mapping tables only. No journal reads."""
        if not partner:
            return []
        partner_ids = [pid for pid in {partner.id, partner.commercial_partner_id.id} if pid]
        if not partner_ids:
            return []
        self.env.cr.execute(
            """
            SELECT vendor_name
              FROM opal_vendor_map
             WHERE partner_id IN %s
               AND vendor_name IS NOT NULL
            """,
            [tuple(partner_ids)],
        )
        names = [row[0] for row in self.env.cr.fetchall() if row[0]]
        if names:
            return names
        clipped = self._clip(partner.name or partner.display_name or '')
        if not clipped:
            return []
        self.env.cr.execute(
            """
            SELECT vendor_name
              FROM opal_vendor_map
             WHERE vendor_name ILIKE %s
            """,
            [clipped],
        )
        names = [row[0] for row in self.env.cr.fetchall() if row[0]]
        if names:
            return names
        self.env.cr.execute(
            """
            SELECT DISTINCT vendor_name
              FROM opal_vendor_project
             WHERE vendor_name ILIKE %s
            """,
            [clipped],
        )
        return [row[0] for row in self.env.cr.fetchall() if row[0]]

    def _project_row_dicts(self, vendor_names, project_filter=None):
        if not vendor_names:
            return []
        self.env.cr.execute(
            """
            SELECT vendor_name, project_code, project_name, debit, credit, balance
              FROM opal_vendor_project
             WHERE vendor_name IN %s
             ORDER BY vendor_name, project_code
            """,
            [tuple(vendor_names)],
        )
        rows = [
            {
                'vendor_name': vendor_name,
                'project_code': project_code,
                'project_name': project_name,
                'debit': debit or 0.0,
                'credit': credit or 0.0,
                'balance': balance or 0.0,
            }
            for vendor_name, project_code, project_name, debit, credit, balance
            in self.env.cr.fetchall()
        ]
        if project_filter is None:
            return rows
        return [row for row in rows if self._row_matches_project(row, project_filter)]

    def _opal_line(self, **values):
        return {
            'id': values['id'],
            'name': values.get('name') or '',
            'level': 1,
            'line_type': 'opal',
            'foldable': False,
            'badge': 'OPAL',
            'partner_id': values.get('partner_id') or False,
            'partner_name': values.get('partner_name') or False,
            'account_id': values.get('account_id') or False,
            'journal_code': False,
            'account_code': False,
            'analytic_name': values.get('analytic_name') or '',
            'date': False,
            'due_date': False,
            'matching_number': False,
            'communication': values.get('communication') or False,
            'amount_currency': False,
            'currency_name': False,
            'debit': values.get('debit', 0.0) or 0.0,
            'credit': values.get('credit', 0.0) or 0.0,
            'balance': values.get('balance', 0.0) or 0.0,
            'children': [],
        }

    def _project_scoped_amounts(self, row, currency):
        """When a project is selected, put OPAL net on credit (payable) or debit."""
        balance = currency.round(row.get('balance') or 0.0)
        if balance >= 0:
            return 0.0, balance, balance
        return abs(balance), 0.0, balance

    def _rows_for_vendor(
        self, vendor_name, rows, partner, account=None, prefix='', project_filter=None, currency=None,
    ):
        vendor_rows = [row for row in rows if row['vendor_name'] == vendor_name]
        if project_filter is not None:
            vendor_rows = [
                row for row in vendor_rows if self._row_matches_project(row, project_filter)
            ]
        if not vendor_rows:
            return []
        partner_id = partner.id if partner else False
        partner_name = partner.display_name if partner else vendor_name
        account_id = account.id if account else False
        currency = currency or self.env.company.currency_id

        # Project filter: only the matching project row(s), no Overall.
        if project_filter is not None:
            lines = []
            for rec in vendor_rows:
                short = self._clip(rec['project_name']) or rec['project_code']
                debit, credit, balance = self._project_scoped_amounts(rec, currency)
                lines.append(self._opal_line(
                    id='%sopal-project:%s:%s:%s' % (
                        prefix, partner_id or 'none', vendor_name, rec['project_code'],
                    ),
                    name='OPAL Project — %s' % short,
                    partner_id=partner_id,
                    partner_name=partner_name,
                    account_id=account_id,
                    analytic_name=short,
                    communication=short,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                ))
            return lines

        overall_debit = sum(row['debit'] for row in vendor_rows)
        overall_credit = sum(row['credit'] for row in vendor_rows)
        overall_balance = sum(row['balance'] for row in vendor_rows)
        first_name = self._clip(vendor_rows[0]['project_name']) if len(vendor_rows) == 1 else 'All projects'
        lines = [self._opal_line(
            id='%sopal-overall:%s:%s' % (prefix, partner_id or 'none', vendor_name),
            name='OPAL Overall',
            partner_id=partner_id,
            partner_name=partner_name,
            account_id=account_id,
            analytic_name=first_name,
            debit=overall_debit,
            credit=overall_credit,
            balance=overall_balance,
        )]
        if len(vendor_rows) == 1:
            return lines
        for rec in vendor_rows:
            short = self._clip(rec['project_name']) or rec['project_code']
            lines.append(self._opal_line(
                id='%sopal-project:%s:%s:%s' % (
                    prefix, partner_id or 'none', vendor_name, rec['project_code'],
                ),
                name='OPAL Project — %s' % short,
                partner_id=partner_id,
                partner_name=partner_name,
                account_id=account_id,
                analytic_name=short,
                communication=short,
                debit=rec['debit'],
                credit=rec['credit'],
                balance=rec['balance'],
            ))
        return lines

    def _unique_commercial_partners(self, partners):
        seen = set()
        unique = []
        records = [partner for partner in partners if partner]
        for partner in self.env['res.partner'].browse(
            [partner.id for partner in records]
        ).exists().sorted(key=lambda rec: rec.display_name or ''):
            commercial = partner.commercial_partner_id
            if commercial.id in seen:
                continue
            seen.add(commercial.id)
            unique.append(commercial)
        return unique

    def get_partners_children_map(self, partners, options, currency):
        """One SQL pass for every partner shown on Unfold All."""
        result = {}
        records = [partner for partner in partners if partner]
        if not options.get('show_opal_balance') or not records:
            return result

        project_filter = self._project_filter(options)
        lookup_ids = set()
        commercial_by_id = {}
        for partner in records:
            commercial = partner.commercial_partner_id
            commercial_by_id[partner.id] = commercial
            lookup_ids.add(partner.id)
            if commercial:
                lookup_ids.add(commercial.id)
        if not lookup_ids:
            return result

        self.env.cr.execute(
            """
            SELECT partner_id, vendor_name
              FROM opal_vendor_map
             WHERE partner_id IN %s
               AND vendor_name IS NOT NULL
            """,
            [tuple(lookup_ids)],
        )
        names_by_partner = defaultdict(list)
        for partner_id, vendor_name in self.env.cr.fetchall():
            if vendor_name:
                names_by_partner[partner_id].append(vendor_name)

        missing = []
        clipped_by_partner = {}
        for partner in records:
            commercial = commercial_by_id[partner.id]
            names = names_by_partner.get(partner.id) or names_by_partner.get(
                commercial.id if commercial else 0
            ) or []
            if names:
                names_by_partner[partner.id] = list(dict.fromkeys(names))
                continue
            clipped = self._clip(partner.name or partner.display_name or '')
            if clipped:
                missing.append(partner)
                clipped_by_partner[partner.id] = clipped

        if missing:
            clips = tuple({clipped_by_partner[partner.id].lower() for partner in missing})
            self.env.cr.execute(
                """
                SELECT vendor_name
                  FROM opal_vendor_map
                 WHERE lower(vendor_name) IN %s
                """,
                [clips],
            )
            map_by_lower = {
                row[0].lower(): row[0] for row in self.env.cr.fetchall() if row[0]
            }
            still = []
            for partner in missing:
                key = clipped_by_partner[partner.id].lower()
                if key in map_by_lower:
                    names_by_partner[partner.id].append(map_by_lower[key])
                else:
                    still.append(partner)
            if still:
                self.env.cr.execute(
                    """
                    SELECT DISTINCT vendor_name
                      FROM opal_vendor_project
                     WHERE lower(vendor_name) IN %s
                    """,
                    [tuple({clipped_by_partner[partner.id].lower() for partner in still})],
                )
                proj_by_lower = {
                    row[0].lower(): row[0] for row in self.env.cr.fetchall() if row[0]
                }
                for partner in still:
                    key = clipped_by_partner[partner.id].lower()
                    if key in proj_by_lower:
                        names_by_partner[partner.id].append(proj_by_lower[key])

        all_names = []
        names_for = {}
        for partner in records:
            names = list(dict.fromkeys(names_by_partner.get(partner.id) or []))
            names_for[partner.id] = names
            all_names.extend(names)
        rows = self._project_row_dicts(list(dict.fromkeys(all_names)), project_filter)
        rows_by_vendor = defaultdict(list)
        for row in rows:
            rows_by_vendor[row['vendor_name']].append(row)

        for partner in records:
            names = names_for[partner.id]
            lines = []
            for vendor_name in sorted(names, key=str.lower):
                lines.extend(self._rows_for_vendor(
                    vendor_name,
                    rows_by_vendor.get(vendor_name, []),
                    partner,
                    project_filter=project_filter,
                    currency=currency,
                ))
            result[partner.id] = lines
        return result

    def get_partner_children(self, partner, options, currency):
        if not options.get('show_opal_balance') or not partner:
            return []
        return self.get_partners_children_map([partner], options, currency).get(partner.id, [])

    def get_accounts_children_map(self, accounts, partner_ids_by_account, options, currency):
        result = {}
        if not options.get('show_opal_balance'):
            return result
        payable_ids = {
            account.id for account in accounts
            if getattr(account, 'account_type', '') == 'liability_payable'
        }
        all_ids = []
        for account in accounts:
            if account.id in payable_ids:
                all_ids.extend(partner_ids_by_account.get(account.id) or [])
        browsed = self.env['res.partner'].browse(list(dict.fromkeys(all_ids))).exists()
        commercial_of = {partner.id: partner.commercial_partner_id for partner in browsed}
        partners = self._unique_commercial_partners(browsed)
        partner_rows = self.get_partners_children_map(partners, options, currency)
        for account in accounts:
            if account.id not in payable_ids:
                result[account.id] = []
                continue
            lines = []
            seen = set()
            for partner_id in partner_ids_by_account.get(account.id) or []:
                commercial = commercial_of.get(partner_id)
                if not commercial or commercial.id in seen:
                    continue
                seen.add(commercial.id)
                for row in partner_rows.get(commercial.id, []):
                    item = dict(row)
                    item['id'] = 'gl-%s' % item['id']
                    item['account_id'] = account.id
                    lines.append(item)
            result[account.id] = lines
        return result

    def get_account_children(self, account, partner_ids, options, currency):
        if not options.get('show_opal_balance') or not account:
            return []
        return self.get_accounts_children_map(
            [account], {account.id: partner_ids or []}, options, currency
        ).get(account.id, [])

    def _partner_ids_to_check(self, options, present_ids):
        selected = [int(pid) for pid in (options.get('partner_ids') or []) if pid]
        if selected:
            return [pid for pid in selected if pid not in present_ids]
        # No partner filter: find every mapped vendor that has OPAL for this project.
        project_filter = self._project_filter(options)
        if project_filter is None:
            return []
        self.env.cr.execute(
            """
            SELECT DISTINCT m.partner_id
              FROM opal_vendor_map m
              JOIN opal_vendor_project p ON p.vendor_name = m.vendor_name
             WHERE m.partner_id IS NOT NULL
            """
        )
        mapped = [row[0] for row in self.env.cr.fetchall() if row[0] and row[0] not in present_ids]
        return mapped

    def _opal_children(self, partner_line):
        return [
            child for child in (partner_line.get('children') or [])
            if child.get('line_type') == 'opal'
        ]

    def _is_project_scoped_opal(self, children):
        if not children:
            return False
        return all('Overall' not in (child.get('name') or '') for child in children)

    def _merge_opal_children(self, partner_line, opal_children):
        """Insert OPAL rows after Initial Balance. Never drop Odoo journal lines."""
        if not opal_children:
            return
        existing = list(partner_line.get('children') or [])
        existing_ids = {child.get('id') for child in existing}
        to_add = [child for child in opal_children if child.get('id') not in existing_ids]
        if not to_add:
            return
        insert_at = 0
        for index, child in enumerate(existing):
            if child.get('line_type') == 'initial':
                insert_at = index + 1
                break
        partner_line['children'] = existing[:insert_at] + to_add + existing[insert_at:]

    def adjust_partner_line(self, partner_line, extra_children, options, currency):
        """Net partner header when a project is selected. Never drop Odoo journal lines."""
        if not partner_line or not options.get('show_opal_balance'):
            return partner_line
        project_filter = self._project_filter(options)
        opal = [row for row in (extra_children or []) if row.get('line_type') == 'opal']
        if not opal:
            opal = self._opal_children(partner_line)
        if project_filter is None and not self._is_project_scoped_opal(opal):
            return partner_line
        if not opal and partner_line.get('partner_id'):
            partner = self.env['res.partner'].browse(partner_line['partner_id']).exists()
            if partner:
                opal = self.get_partner_children(partner, options, currency)
        if not opal:
            return partner_line
        self._merge_opal_children(partner_line, opal)
        self._apply_project_opal_netting(partner_line, currency, options)
        return partner_line

    def _apply_project_opal_netting(self, partner_line, currency, options=None):
        """Adjust partner/total amounts by OPAL. Leave Odoo journal lines untouched."""
        if partner_line.get('opal_netted'):
            return
        children = self._opal_children(partner_line)
        if not children and options and partner_line.get('partner_id'):
            partner = self.env['res.partner'].browse(partner_line['partner_id']).exists()
            if partner:
                children = self.get_partner_children(partner, options, currency)
                self._merge_opal_children(partner_line, children)
        if not children:
            return
        opal_debit = sum(child.get('debit') or 0.0 for child in children)
        opal_credit = sum(child.get('credit') or 0.0 for child in children)
        odoo_debit = partner_line.get('odoo_debit')
        if odoo_debit is None:
            odoo_debit = partner_line.get('debit') or 0.0
        odoo_credit = partner_line.get('odoo_credit')
        if odoo_credit is None:
            odoo_credit = partner_line.get('credit') or 0.0
        odoo_balance = partner_line.get('odoo_balance')
        if odoo_balance is None:
            odoo_balance = partner_line.get('balance') or 0.0
        partner_line['odoo_debit'] = odoo_debit
        partner_line['odoo_credit'] = odoo_credit
        partner_line['odoo_balance'] = odoo_balance
        partner_line['debit'] = currency.round(odoo_debit + opal_debit)
        partner_line['credit'] = currency.round(odoo_credit + opal_credit)
        partner_line['balance'] = currency.round(odoo_balance + opal_debit - opal_credit)
        partner_line['foldable'] = True
        partner_line['opal_netted'] = True

    def _opal_only_partner_line(self, partner, children, currency):
        debit = currency.round(sum(child.get('debit') or 0.0 for child in children))
        credit = currency.round(sum(child.get('credit') or 0.0 for child in children))
        return {
            'id': 'partner_%s' % partner.id,
            'name': partner.display_name,
            'level': 0,
            'line_type': 'partner',
            'foldable': True,
            'partner_id': partner.id,
            'journal_code': False,
            'account_code': False,
            'analytic_name': '',
            'date': False,
            'due_date': False,
            'matching_number': False,
            'amount_currency': False,
            'currency_name': False,
            'debit': debit,
            'credit': credit,
            'balance': currency.round(debit - credit),
            'children': list(children),
            'opal_only': True,
            'opal_netted': True,
        }

    def enrich_partner_ledger_data(self, engine, data):
        """Project-scoped OPAL netting + inject partners with OPAL but no Odoo lines.

        Only runs when Show OPAL is on. Without a project filter, rows stay as-is.
        Never writes journals.
        """
        options = engine.options
        if not options.get('show_opal_balance'):
            return data
        project_filter = self._project_filter(options)
        currency = engine.currency
        lines = list(data.get('lines') or [])
        if not lines:
            body, total = [], None
        elif lines[-1].get('line_type') == 'total':
            body, total = lines[:-1], lines[-1]
        else:
            body, total = lines, None

        if project_filter is not None:
            for line in body:
                if line.get('line_type') == 'partner':
                    self._apply_project_opal_netting(line, currency, options)

            present = {
                line.get('partner_id')
                for line in body
                if line.get('line_type') == 'partner' and line.get('partner_id')
            }
            missing_ids = self._partner_ids_to_check(options, present)
            if missing_ids:
                partners = self.env['res.partner'].browse(missing_ids).exists()
                children_map = self.get_partners_children_map(partners, options, currency)
                for partner in partners.sorted(key=lambda rec: rec.display_name or ''):
                    children = children_map.get(partner.id) or []
                    if not children:
                        continue
                    body.append(self._opal_only_partner_line(partner, children, currency))

            body.sort(key=lambda line: (
                0 if line.get('line_type') == 'partner' else 1,
                (line.get('name') or '').lower(),
            ))
        else:
            for line in body:
                if (
                    line.get('line_type') == 'partner'
                    and self._is_project_scoped_opal(self._opal_children(line))
                ):
                    self._apply_project_opal_netting(line, currency, options)

        if total is not None:
            partners = [line for line in body if line.get('line_type') == 'partner']
            total_debit = sum(line.get('debit') or 0.0 for line in partners)
            total_credit = sum(line.get('credit') or 0.0 for line in partners)
            total['debit'] = currency.round(total_debit)
            total['credit'] = currency.round(total_credit)
            total['balance'] = currency.round(total_debit - total_credit)
            data['lines'] = body + [total]
        else:
            data['lines'] = body
        return data

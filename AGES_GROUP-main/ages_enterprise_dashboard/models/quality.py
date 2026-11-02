# -*- coding: utf-8 -*-

from odoo import models


class AgesEnterpriseDashboardQuality(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def get_data_quality_dashboard(self, filters=None):
        scope = self._normalize_filters(filters)
        date_from, date_to = scope['date_from'], scope['date_to']
        cards = []
        warnings = []

        def add_card(key, title, coverage, action_key, why):
            if coverage is False:
                cards.append({
                    'key': key,
                    'title': title,
                    'percent': False,
                    'assigned': 0,
                    'missing': 0,
                    'total': 0,
                    'available': False,
                    'why': why,
                    'action_key': action_key,
                })
                return
            cards.append({
                'key': key,
                'title': title,
                'percent': coverage['percent'],
                'assigned': coverage['assigned'],
                'missing': coverage['missing'],
                'total': coverage['total'],
                'available': True,
                'why': why,
                'action_key': action_key,
            })

        if self._can_read('account.move.line'):
            domain = self._aml_posted_domain(scope) + self._date_domain('date', date_from, date_to)
            add_card(
                'analytic',
                'Posted journal items with analytic distribution',
                self._coverage_ratio('account.move.line', domain, [('analytic_distribution', '!=', False)]),
                'aml_expense',
                'Count of posted AML in the period with analytic_distribution set. Amount-level project P&L is incomplete below 100%.',
            )
            amount_total = abs(self._read_group_sum('account.move.line', domain, 'balance') or 0.0)
            amount_assigned = abs(self._read_group_sum(
                'account.move.line', domain + [('analytic_distribution', '!=', False)], 'balance'
            ) or 0.0)
            unassigned_amount = max(amount_total - amount_assigned, 0.0) if amount_total else 0.0
            warnings.append(
                'Posted AML balance with analytic distribution: %s of %s in this period.'
                % (self._format_money(amount_assigned, scope), self._format_money(amount_total, scope))
            )
            if unassigned_amount:
                warnings.append(
                    'Unassigned analytic balance in this period: %s.'
                    % self._format_money(unassigned_amount, scope)
                )
        else:
            add_card('analytic', 'Posted journal items with analytic distribution', False, False,
                     'account.move.line is not readable.')

        if self._can_read('purchase.order'):
            po_domain = self._scope_domain('purchase.order', scope) + self._date_domain('date_order', date_from, date_to)
            project_path = self._project_path('purchase.order')
            if project_path:
                add_card(
                    'po_project',
                    'Purchase orders with a project',
                    self._coverage_ratio('purchase.order', po_domain, [(project_path, '!=', False)]),
                    'purchase_orders',
                    'Uses %s on purchase.order.' % project_path,
                )
            else:
                add_card('po_project', 'Purchase orders with a project', False, 'purchase_orders',
                         'No project field exists on purchase.order in this database.')
        else:
            add_card('po_project', 'Purchase orders with a project', False, False, 'Purchase orders are not readable.')

        if self._can_read('account.move'):
            bill_domain = self._scope_domain('account.move', scope, [
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '=', 'posted'),
            ]) + self._date_domain('invoice_date', date_from, date_to)
            if self._has_field('account.move', 'invoice_origin'):
                add_card(
                    'bill_origin',
                    'Vendor bills with a source document',
                    self._coverage_ratio('account.move', bill_domain, [('invoice_origin', '!=', False)]),
                    'vendor_bills',
                    'Posted vendor bills whose invoice_origin is set (typically a purchase order).',
                )
            else:
                add_card('bill_origin', 'Vendor bills with a source document', False, 'vendor_bills',
                         'account.move.invoice_origin is not present.')
        else:
            add_card('bill_origin', 'Vendor bills with a source document', False, False, 'Invoices are not readable.')

        if self._can_read('ages.running.bill'):
            ra_domain = self._scope_domain('ages.running.bill', scope, [('state', '=', 'confirmed')])
            if self._has_field('ages.running.bill', 'invoice_id'):
                add_card(
                    'ra_invoice',
                    'Confirmed running bills linked to an invoice',
                    self._coverage_ratio('ages.running.bill', ra_domain, [('invoice_id', '!=', False)]),
                    'running_bills',
                    'Confirmed RA documents with invoice_id set.',
                )
            else:
                add_card('ra_invoice', 'Confirmed running bills linked to an invoice', False, 'running_bills',
                         'ages.running.bill.invoice_id is not present.')
        else:
            add_card('ra_invoice', 'Confirmed running bills linked to an invoice', False, False,
                     'Running bills are not installed or not readable.')

        if self._can_read('project.portal.attendance') and self._has_field('project.portal.attendance', 'sync_state'):
            portal_domain = self._scope_domain('project.portal.attendance', scope) + self._date_domain('date', date_from, date_to)
            add_card(
                'portal_sync',
                'Portal attendance rows synced',
                self._coverage_ratio('project.portal.attendance', portal_domain, [('sync_state', '=', 'synced')]),
                'portal_attendance',
                'Rows whose sync_state is synced. Do not add portal rows to hr.attendance counts.',
            )
        else:
            add_card('portal_sync', 'Portal attendance rows synced', False, False,
                     'project.portal.attendance.sync_state is not readable.')

        if self._capability_map().get('payroll') and self._has_field('hr.payslip', 'move_id'):
            slip_domain = self._scope_domain('hr.payslip', scope, [('state', 'in', ('done', 'paid'))])
            slip_domain += self._date_domain('date_from', date_from, date_to)
            add_card(
                'payslip_move',
                'Finalized payslips linked to a journal entry',
                self._coverage_ratio('hr.payslip', slip_domain, [('move_id', '!=', False)]),
                'payslips',
                'Requires ages_hr_payroll_account. Only done/paid slips in the selected period.',
            )
        else:
            add_card('payslip_move', 'Finalized payslips linked to a journal entry', False, False,
                     'Payslip accounting link is hidden unless payroll access and move_id exist.')

        percents = [card['percent'] for card in cards if card.get('available') and card.get('percent') is not False]
        kpis = [
            self._kpi(
                scope, 'indicators', 'Quality indicators', len(cards), False, False,
                'Number of data-quality checks evaluated for this user and scope.',
                suffix='', basis='count', date_field='', formula='Count of coverage checks.',
            ),
            self._kpi(
                scope, 'average', 'Average coverage', (sum(percents) / len(percents)) if percents else 0.0, False, False,
                'Mean of available coverage percentages. Not a weighted data-quality score.',
                suffix='%', basis='ratio', date_field='', formula='Mean of available coverage percents.',
            ),
            self._kpi(
                scope, 'gaps', 'Open gaps', sum(card.get('missing') or 0 for card in cards if card.get('available')),
                False, False, 'Sum of records missing the required link or distribution.',
                suffix='', basis='count', date_field='', formula='Sum of missing counts.',
            ),
        ]
        tables = {
            'quality': self._mgmt_table('Coverage detail', [
                {'key': 'title', 'label': 'Check'},
                {'key': 'assigned', 'label': 'Assigned'},
                {'key': 'missing', 'label': 'Missing'},
                {'key': 'percent', 'label': 'Coverage'},
                {'key': 'why', 'label': 'Basis'},
            ], [{
                'title': card['title'],
                'assigned': card['assigned'] if card['available'] else '—',
                'missing': card['missing'] if card['available'] else '—',
                'percent': ('%s%%' % card['percent']) if card['available'] else 'Unavailable',
                'why': card['why'],
                'action_key': card.get('action_key'),
            } for card in cards]),
        }
        return self._payload(
            scope, 'quality_data', kpis, {}, tables,
            extra={
                'quality_cards': cards,
                'layout': self._dashboard_layout(
                    kind='quality',
                    hero=['indicators', 'average', 'gaps'],
                    quality=[card.get('key') for card in cards if card.get('key')],
                    tables=['quality'],
                ),
            },
            warnings=warnings or ['Coverage uses record counts in the current scope, not invented completeness scores.'],
        )

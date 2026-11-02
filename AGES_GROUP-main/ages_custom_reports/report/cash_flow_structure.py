# -*- coding: utf-8 -*-
"""Cash Flow Statement line hierarchy mirroring Odoo Enterprise account_reports."""

from odoo import _

# Ordered layout — indentation reflects report structure.
CASH_FLOW_LAYOUT = {
    'opening_balance': {
        'name': lambda env: _('Cash and cash equivalents, beginning of period'),
        'level': 0,
        'line_type': 'section',
        'foldable': True,
    },
    'net_increase': {
        'name': lambda env: _('Net increase in cash and cash equivalents'),
        'level': 0,
        'line_type': 'total',
        'foldable': True,
        'children': [
            'operating_activities',
            'investing_activities',
            'financing_activities',
            'unclassified_activities',
        ],
    },
    'operating_activities': {
        'name': lambda env: _('Cash flows from operating activities'),
        'level': 2,
        'line_type': 'group',
        'parent_id': 'net_increase',
        'foldable': True,
        'children': [
            'advance_payments_customer',
            'received_operating_activities',
            'advance_payments_suppliers',
            'paid_operating_activities',
        ],
    },
    'advance_payments_customer': {
        'name': lambda env: _('Advance Payments received from customers'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'operating_activities',
        'foldable': True,
    },
    'received_operating_activities': {
        'name': lambda env: _('Cash received from operating activities'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'operating_activities',
        'foldable': True,
    },
    'advance_payments_suppliers': {
        'name': lambda env: _('Advance payments made to suppliers'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'operating_activities',
        'foldable': True,
    },
    'paid_operating_activities': {
        'name': lambda env: _('Cash paid for operating activities'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'operating_activities',
        'foldable': True,
    },
    'investing_activities': {
        'name': lambda env: _('Cash flows from investing & extraordinary activities'),
        'level': 2,
        'line_type': 'group',
        'parent_id': 'net_increase',
        'foldable': True,
        'children': [
            'investing_activities_cash_in',
            'investing_activities_cash_out',
        ],
    },
    'investing_activities_cash_in': {
        'name': lambda env: _('Cash in'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'investing_activities',
        'foldable': True,
    },
    'investing_activities_cash_out': {
        'name': lambda env: _('Cash out'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'investing_activities',
        'foldable': True,
    },
    'financing_activities': {
        'name': lambda env: _('Cash flows from financing activities'),
        'level': 2,
        'line_type': 'group',
        'parent_id': 'net_increase',
        'foldable': True,
        'children': [
            'financing_activities_cash_in',
            'financing_activities_cash_out',
        ],
    },
    'financing_activities_cash_in': {
        'name': lambda env: _('Cash in'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'financing_activities',
        'foldable': True,
    },
    'financing_activities_cash_out': {
        'name': lambda env: _('Cash out'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'financing_activities',
        'foldable': True,
    },
    'unclassified_activities': {
        'name': lambda env: _('Cash flows from unclassified activities'),
        'level': 2,
        'line_type': 'group',
        'parent_id': 'net_increase',
        'foldable': True,
        'children': [
            'unclassified_activities_cash_in',
            'unclassified_activities_cash_out',
        ],
    },
    'unclassified_activities_cash_in': {
        'name': lambda env: _('Cash in'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'unclassified_activities',
        'foldable': True,
    },
    'unclassified_activities_cash_out': {
        'name': lambda env: _('Cash out'),
        'level': 4,
        'line_type': 'group',
        'parent_id': 'unclassified_activities',
        'foldable': True,
    },
    'closing_balance': {
        'name': lambda env: _('Cash and cash equivalents, closing balance'),
        'level': 0,
        'line_type': 'section',
        'foldable': True,
    },
}

# Top-level display order.
CASH_FLOW_ROOT_ORDER = [
    'opening_balance',
    'net_increase',
    'closing_balance',
]

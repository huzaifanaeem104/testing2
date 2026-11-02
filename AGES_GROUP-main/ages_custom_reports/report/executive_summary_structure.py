# -*- coding: utf-8 -*-
"""Executive Summary sections mirroring Odoo Enterprise account_reports."""

EXECUTIVE_SUMMARY_SECTIONS = [
    {
        'code': 'CASH',
        'name': 'Cash',
        'line_type': 'section',
        'children': [
            {'code': 'cash_received', 'name': 'Cash received', 'figure_type': 'monetary'},
            {'code': 'cash_spent', 'name': 'Cash spent', 'figure_type': 'monetary', 'invert_display': True},
            {'code': 'cash_surplus', 'name': 'Cash surplus', 'figure_type': 'monetary'},
            {'code': 'closing_bank_balance', 'name': 'Closing bank balance', 'figure_type': 'monetary'},
        ],
    },
    {
        'code': 'PROFIT',
        'name': 'Profitability',
        'line_type': 'section',
        'children': [
            {'code': 'revenue', 'name': 'Revenue', 'figure_type': 'monetary'},
            {'code': 'cost_of_revenue', 'name': 'Cost of Revenue', 'figure_type': 'monetary'},
            {'code': 'gross_profit', 'name': 'Gross profit', 'figure_type': 'monetary'},
            {'code': 'expenses', 'name': 'Expenses', 'figure_type': 'monetary'},
            {'code': 'net_profit', 'name': 'Net Profit', 'figure_type': 'monetary'},
        ],
    },
    {
        'code': 'BS',
        'name': 'Balance Sheet',
        'line_type': 'section',
        'children': [
            {'code': 'receivables', 'name': 'Receivables', 'figure_type': 'monetary'},
            {'code': 'payables', 'name': 'Payables', 'figure_type': 'monetary'},
            {'code': 'net_assets', 'name': 'Net assets', 'figure_type': 'monetary'},
        ],
    },
    {
        'code': 'PERF',
        'name': 'Performance',
        'line_type': 'section',
        'children': [
            {
                'code': 'gross_profit_margin',
                'name': 'Gross profit margin (gross profit / operating income)',
                'figure_type': 'percentage',
            },
            {
                'code': 'net_profit_margin',
                'name': 'Net profit margin (net profit / revenue)',
                'figure_type': 'percentage',
            },
            {
                'code': 'return_on_investments',
                'name': 'Return on investments (net profit / assets)',
                'figure_type': 'percentage',
            },
        ],
    },
    {
        'code': 'POS',
        'name': 'Position',
        'line_type': 'section',
        'children': [
            {'code': 'avg_debtors_days', 'name': 'Average debtors days', 'figure_type': 'float'},
            {'code': 'avg_creditors_days', 'name': 'Average creditors days', 'figure_type': 'float'},
            {'code': 'short_term_cash_forecast', 'name': 'Short term cash forecast', 'figure_type': 'monetary'},
            {'code': 'current_assets_to_liabilities', 'name': 'Current assets to liabilities', 'figure_type': 'float'},
        ],
    },
]

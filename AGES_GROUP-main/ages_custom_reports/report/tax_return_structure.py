# -*- coding: utf-8 -*-
"""Pakistan Tax Return line tree, mirrored from l10n_pk account_tax_vat_report.xml."""


def _tag_line(code, name, base_tag=None, tax_tag=None):
    return {
        'id': code,
        'code': code,
        'name': name,
        'line_type': 'tax',
        'show_base': True,
        'show_tax': True,
        'base_tag': base_tag or f'{name} (Base)',
        'tax_tag': tax_tag or f'{name} (Tax)',
        'children': [],
    }


def _agg_line(code, name, tax_formula, children=None, line_type='total'):
    return {
        'id': code,
        'code': code,
        'name': name,
        'line_type': line_type,
        'show_base': False,
        'show_tax': True,
        'tax_formula': tax_formula,
        'children': children or [],
    }


def _section(code, name, children, tax_formula=None, show_tax=False):
    return {
        'id': code,
        'code': code,
        'name': name,
        'line_type': 'section',
        'foldable': True,
        'show_base': False,
        'show_tax': show_tax,
        'tax_formula': tax_formula,
        'children': children,
    }


PURCHASE_TAX_LINES = [
    _tag_line('PUR_ST_17', 'Standard Purchases Tax 17%'),
    _tag_line('PUR_TL', 'Purchases Telecommunication Services Tax 19.5%'),
    _tag_line('PUR_SR_17', 'Purchases Services Tax 17%'),
    _tag_line('PUR_SR_16', 'Purchases Services Tax 16%'),
    _tag_line('PUR_SR_15', 'Purchases Services Tax 15%'),
    _tag_line('PUR_SR_13', 'Purchases Services Tax 13%'),
    _tag_line('PUR_SR_10', 'Purchases Services Tax 10%'),
    _tag_line('PUR_SR_8', 'Purchases Services Tax 8%'),
    _tag_line('PUR_SR_5', 'Purchases Services Tax 5%'),
    _tag_line('PUR_SR_3', 'Purchases Services Tax 3%'),
    _tag_line('PUR_SR_2', 'Purchases Services Tax 2%'),
    _tag_line('PUR_SR_1', 'Purchases Services Tax 1%'),
    _tag_line('PUR_SR_0', 'Purchases Services Tax 0%'),
    _tag_line('PUR_PUN', 'Standard Purchases Service Tax Punjab 16%'),
    _tag_line('PUR_ICT', 'Standard Purchases Service Tax ICT 16%'),
    _tag_line('PUR_AJK', 'Standard Purchases Service Tax AJK 16%'),
    _tag_line('PUR_KP', 'Standard Purchases Service Tax KP 15%'),
    _tag_line('PUR_BAL', 'Standard Purchases Service Tax Balochistan 15%'),
    _tag_line('PUR_SIN', 'Standard Purchases Service Tax Sindh 13%'),
]

SALE_TAX_LINES = [
    _tag_line('SAL_ST_17', 'Standard Sales Tax 17%'),
    _tag_line('SAL_TL', 'Sales Tax Telecommunication Services 19.5%'),
    _tag_line('SAL_SR_17', 'Sales Services Tax 17%'),
    _tag_line('SAL_SR_16', 'Sales Services Tax 16%'),
    _tag_line('SAL_SR_15', 'Sales Services Tax 15%'),
    _tag_line('SAL_SR_13', 'Sales Services Tax 13%'),
    _tag_line('SAL_SR_10', 'Sales Services Tax 10%'),
    _tag_line('SAL_SR_8', 'Sales Services Tax 8%'),
    _tag_line('SAL_SR_5', 'Sales Services Tax 5%'),
    _tag_line('SAL_SR_3', 'Sales Services Tax 3%'),
    _tag_line('SAL_SR_2', 'Sales Services Tax 2%'),
    _tag_line('SAL_SR_1', 'Sales Services Tax 1%'),
    _tag_line('SAL_SR_0', 'Sales Services Tax 0%'),
    _tag_line('SAL_PUN', 'Standard Sales Service Tax Punjab 16%'),
    _tag_line('SAL_ICT', 'Standard Sales Service Tax ICT 16%'),
    _tag_line('SAL_AJK', 'Standard Sales Service Tax AJK 16%'),
    _tag_line('SAL_KP', 'Standard Sales Service Tax KP 15%'),
    _tag_line('SAL_BAL', 'Standard Sales Service Tax Balochistan 15%'),
    _tag_line(
        'SAL_SIN',
        'Standard Sales Tax Services 13% Sindh',
        base_tag='Standard Sales Tax Services 13% Sindh (Base)',
        tax_tag='Standard Sales Tax Services 13% Sindh (Tax)',
    ),
]

NET_SERVICE_SALES_FORMULA = (
    'SAL_TL.tax + SAL_SR_17.tax + SAL_SR_16.tax + SAL_SR_15.tax + SAL_SR_13.tax '
    '+ SAL_SR_10.tax + SAL_SR_8.tax + SAL_SR_5.tax + SAL_SR_3.tax + SAL_SR_2.tax '
    '+ SAL_SR_1.tax + SAL_SR_0.tax'
)
NET_SERVICE_PURCHASES_FORMULA = (
    'PUR_TL.tax + PUR_SR_17.tax + PUR_SR_16.tax + PUR_SR_15.tax + PUR_SR_13.tax '
    '+ PUR_SR_10.tax + PUR_SR_8.tax + PUR_SR_5.tax + PUR_SR_3.tax + PUR_SR_2.tax '
    '+ PUR_SR_1.tax + PUR_SR_0.tax'
)

TAX_RETURN_STRUCTURE = [
    _section('PURCHASES', 'Purchases Taxes', PURCHASE_TAX_LINES),
    _section('SALES', 'Sales Taxes', SALE_TAX_LINES),
    _section(
        'NET_STANDARD_TAX',
        'Net Standard Tax',
        [
            _agg_line('SAL_NS_TAX', 'Net Standard Tax Sales (Payable)', 'SAL_ST_17.tax'),
            _agg_line('PUR_NS_TAX', 'Net Standard Tax Purchases (Recoverable)', 'PUR_ST_17.tax'),
        ],
        tax_formula='SAL_NS_TAX.tax - PUR_NS_TAX.tax',
        show_tax=True,
    ),
    _section(
        'NET_SERVICE_TAX',
        'Net Service Tax',
        [
            _agg_line('SAL_NST_TAX', 'Net Service Tax Sales (Payable)', NET_SERVICE_SALES_FORMULA),
            _agg_line(
                'PUR_NST_TAX',
                'Net Service Tax Purchases (Recoverable)',
                NET_SERVICE_PURCHASES_FORMULA,
            ),
        ],
        tax_formula='SAL_NST_TAX.tax - PUR_NST_TAX.tax',
        show_tax=True,
    ),
    _section(
        'NET_PROVINCE',
        'Net Standard Service Tax Per Province',
        [
            _agg_line('SAL_NSTP_PUN_TAX', 'Net Due Punjab Tax', 'SAL_PUN.tax - PUR_PUN.tax'),
            _agg_line('SAL_NSTP_ICT_TAX', 'Net Due ICT', 'SAL_ICT.tax - PUR_ICT.tax'),
            _agg_line('SAL_NSTP_AJK_TAX', 'Net Due AJK', 'SAL_AJK.tax - PUR_AJK.tax'),
            _agg_line('SAL_NSTP_KP_TAX', 'Net Due KP', 'SAL_KP.tax - PUR_KP.tax'),
            _agg_line('SAL_NSTP_BAL_TAX', 'Net Due Balochistan', 'SAL_BAL.tax - PUR_BAL.tax'),
            _agg_line('SAL_NSTP_SIN_TAX', 'Net Due Sindh', 'SAL_SIN.tax - PUR_SIN.tax'),
        ],
    ),
]

TAX_RETURN_REPORT_NAME = 'Tax Report Pakistan (PK) (PK)'

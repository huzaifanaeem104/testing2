# -*- coding: utf-8 -*-

import io
import zipfile
from collections import defaultdict
from xml.etree import ElementTree as ET

from odoo.exceptions import UserError

NS = {
    'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pr': 'http://schemas.openxmlformats.org/package/2006/relationships',
}
NSURI = NS['m']

SHEET_VENDOR_PROJECT = 'Vendor_by_Project'
SHEET_VENDOR_ACCOUNT = 'Vendor_Project_Account'
SHEET_VENDOR_TOTAL = 'Vendor_Totals'
SHEET_PROJECT_TOTAL = 'Project_Totals'
SHEET_CLIENT_PROJECT = 'Client_by_Project'
SHEET_CLIENT_ACCOUNT = 'Client_Project_Account'
SHEET_CLIENT_TOTAL = 'Client_Totals'
SHEET_PROJECT_CLIENT_TOTAL = 'Project_Client_Totals'
VENDOR_SHEETS = (
    SHEET_VENDOR_PROJECT,
    SHEET_VENDOR_ACCOUNT,
    SHEET_VENDOR_TOTAL,
    SHEET_PROJECT_TOTAL,
)
CLIENT_SHEETS = (
    SHEET_CLIENT_PROJECT,
    SHEET_CLIENT_ACCOUNT,
    SHEET_CLIENT_TOTAL,
    SHEET_PROJECT_CLIENT_TOTAL,
)
KNOWN_SHEETS = VENDOR_SHEETS + CLIENT_SHEETS
REQUIRED_SHEETS = VENDOR_SHEETS + (SHEET_CLIENT_PROJECT,)
SHEET_NAME_ALIASES = {
    name.strip().replace(' ', '_').replace('-', '_').lower(): name
    for name in KNOWN_SHEETS
}
SHEET_NAME_ALIASES.update({
    'clients_by_project': SHEET_CLIENT_PROJECT,
    'client_by_project': SHEET_CLIENT_PROJECT,
    'customer_by_project': SHEET_CLIENT_PROJECT,
})

HEADER_ALIASES = {
    'vendor': 'vendor',
    'client': 'vendor',
    'customer': 'vendor',
    'party': 'vendor',
    'project code': 'project_code',
    'project name': 'project_name',
    'category': 'category',
    'account name': 'account_name',
    'account nos': 'account_nos',
    'account no': 'account_no',
    'debit': 'debit',
    'credit': 'credit',
    'balance': 'balance',
    'balance (cr-dr)': 'balance',
    'overall balance (cr-dr)': 'balance',
    'balance (dr-cr)': 'balance',
    'overall balance (dr-cr)': 'balance',
    'projects': 'projects',
    'vendors': 'vendors',
    'clients': 'vendors',
    'voucher lines': 'voucher_lines',
    'subsidiary codes': 'subsidiary_codes',
    'accounts': 'accounts',
    'project codes': 'project_codes',
}


def _xe(value):
    return ('' if value is None else str(value)).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _col_letter(number):
    text = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        text = chr(65 + remainder) + text
    return text


def _col_index(cell_ref):
    letters = ''.join(char for char in (cell_ref or '') if char.isalpha())
    number = 0
    for char in letters:
        number = number * 26 + (ord(char.upper()) - 64)
    return number - 1


def _to_float(value):
    if value in (None, '', False):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(',', '').strip()
    if not text:
        return 0.0
    return float(text)


def _norm_text(value):
    return ('' if value is None else str(value)).strip()


def normalize_project_code(value):
    text = _norm_text(value)
    return text or '(Unallocated)'


def _canonical_sheet_name(name):
    raw = (name or '').strip()
    key = raw.replace(' ', '_').replace('-', '_').lower()
    return SHEET_NAME_ALIASES.get(key, raw)


def parse_workbook(data):
    """Parse vendor and client sheets from the OPAL workbook."""
    if not data:
        raise UserError('Please upload the OPAL Vendor Balance by Project workbook.')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise UserError('The uploaded file is not a valid Excel workbook.') from error

    workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
    rid_to_target = {
        rel.attrib.get('Id'): rel.attrib.get('Target')
        for rel in rels
    }
    shared = _load_shared_strings(archive)
    sheets = {}
    for sheet in workbook.findall('m:sheets/m:sheet', NS):
        name = _canonical_sheet_name(sheet.attrib.get('name'))
        rid = sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        target = rid_to_target.get(rid) or ''
        if target.startswith('/'):
            path = target.lstrip('/')
        elif target.startswith('worksheets/'):
            path = 'xl/' + target
        elif target.startswith('../'):
            path = 'xl/' + target.replace('../', '')
        else:
            path = 'xl/' + target
        if name in KNOWN_SHEETS:
            sheets[name] = _parse_sheet_rows(archive.read(path), shared)

    missing = [name for name in REQUIRED_SHEETS if name not in sheets]
    if missing:
        raise UserError(
            'Workbook is missing required sheet(s): %s. '
            'Upload OPAL Vendor Balance by Project.xlsx (combined vendors + clients). '
            'The client-only workbook will not import.'
            % ', '.join(missing)
        )
    return sheets


def _load_shared_strings(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    values = []
    for item in root.findall('m:si', NS):
        values.append(''.join((node.text or '') for node in item.findall('.//m:t', NS)))
    return values


def _parse_sheet_rows(xml_bytes, shared):
    root = ET.fromstring(xml_bytes)
    headers = []
    rows = []
    for row in root.findall('m:sheetData/m:row', NS):
        values = {}
        for cell in row.findall('m:c', NS):
            ref = cell.attrib.get('r', '')
            values[_col_index(ref)] = _cell_value(cell, shared)
        if not any(_norm_text(value) or value not in (None, '', 0, 0.0) for value in values.values()):
            continue
        if not headers:
            max_col = max(values) if values else -1
            raw = [_norm_text(values.get(index)) for index in range(max_col + 1)]
            headers = [HEADER_ALIASES.get(title.lower(), '') for title in raw]
            if not any(headers):
                raise UserError('Could not read column headers from the workbook.')
            continue
        record = {}
        for index, key in enumerate(headers):
            if not key:
                continue
            record[key] = values.get(index)
        rows.append(record)
    return rows


def _cell_value(cell, shared):
    cell_type = cell.attrib.get('t')
    value_el = cell.find('m:v', NS)
    inline = cell.find('m:is', NS)
    raw = None
    if inline is not None:
        raw = ''.join((node.text or '') for node in inline.findall('.//m:t', NS))
    elif value_el is not None:
        raw = value_el.text
    if cell_type == 's' and raw not in (None, ''):
        try:
            return shared[int(raw)]
        except (TypeError, ValueError, IndexError):
            return raw
    if cell_type in ('n', None) and raw not in (None, ''):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return raw
    return raw


def rows_from_vendor_project(records, balance_fn=None):
    balance_fn = balance_fn or (lambda debit, credit: credit - debit)
    rows = []
    for record in records:
        vendor = _norm_text(record.get('vendor'))
        if not vendor:
            continue
        debit = _to_float(record.get('debit'))
        credit = _to_float(record.get('credit'))
        balance = record.get('balance')
        balance = _to_float(balance) if balance not in (None, '') else balance_fn(debit, credit)
        rows.append({
            'vendor_name': vendor,
            'project_code': normalize_project_code(record.get('project_code')),
            'project_name': _norm_text(record.get('project_name')),
            'debit': debit,
            'credit': credit,
            'balance': balance,
        })
    return rows


def rows_from_vendor_account(records, balance_fn=None):
    balance_fn = balance_fn or (lambda debit, credit: credit - debit)
    rows = []
    for record in records:
        vendor = _norm_text(record.get('vendor'))
        if not vendor:
            continue
        debit = _to_float(record.get('debit'))
        credit = _to_float(record.get('credit'))
        balance = record.get('balance')
        balance = _to_float(balance) if balance not in (None, '') else balance_fn(debit, credit)
        rows.append({
            'vendor_name': vendor,
            'project_code': normalize_project_code(record.get('project_code')),
            'project_name': _norm_text(record.get('project_name')),
            'category': _norm_text(record.get('category')),
            'account_name': _norm_text(record.get('account_name')),
            'debit': debit,
            'credit': credit,
            'balance': balance,
        })
    return rows


def rows_from_vendor_total(records):
    rows = []
    for record in records:
        vendor = _norm_text(record.get('vendor'))
        if not vendor:
            continue
        rows.append({
            'vendor_name': vendor,
            'projects': int(_to_float(record.get('projects'))),
            'debit': _to_float(record.get('debit')),
            'credit': _to_float(record.get('credit')),
            'balance': _to_float(record.get('balance')),
        })
    return rows


def rows_from_project_total(records):
    rows = []
    for record in records:
        code = normalize_project_code(record.get('project_code'))
        if not _norm_text(record.get('project_code')) and not record.get('debit') and not record.get('credit'):
            continue
        rows.append({
            'project_code': code,
            'project_name': _norm_text(record.get('project_name')),
            'vendors': int(_to_float(record.get('vendors'))),
            'debit': _to_float(record.get('debit')),
            'credit': _to_float(record.get('credit')),
            'balance': _to_float(record.get('balance')),
        })
    return rows


def recompute_vendor_totals(project_rows):
    grouped = defaultdict(lambda: {'debit': 0.0, 'credit': 0.0, 'balance': 0.0, 'projects': set()})
    for row in project_rows:
        bucket = grouped[row['vendor_name']]
        bucket['debit'] += row['debit']
        bucket['credit'] += row['credit']
        bucket['balance'] += row['balance']
        bucket['projects'].add(row['project_code'])
    return [
        {
            'vendor_name': vendor,
            'projects': len(data['projects']),
            'debit': data['debit'],
            'credit': data['credit'],
            'balance': data['balance'],
        }
        for vendor, data in grouped.items()
    ]


def recompute_project_totals(project_rows):
    grouped = defaultdict(lambda: {
        'debit': 0.0, 'credit': 0.0, 'balance': 0.0, 'vendors': set(), 'project_name': '',
    })
    for row in project_rows:
        bucket = grouped[row['project_code']]
        bucket['debit'] += row['debit']
        bucket['credit'] += row['credit']
        bucket['balance'] += row['balance']
        bucket['vendors'].add(row['vendor_name'])
        bucket['project_name'] = bucket['project_name'] or row.get('project_name') or ''
    return [
        {
            'project_code': code,
            'project_name': data['project_name'],
            'vendors': len(data['vendors']),
            'debit': data['debit'],
            'credit': data['credit'],
            'balance': data['balance'],
        }
        for code, data in grouped.items()
    ]


def assert_totals_match(project_rows, vendor_totals, project_totals, precision=0.01):
    recomputed_vendors = {
        row['vendor_name']: row for row in recompute_vendor_totals(project_rows)
    }
    for expected in vendor_totals:
        actual = recomputed_vendors.get(expected['vendor_name'])
        if not actual:
            raise UserError(
                'Vendor_Totals has %s but Vendor_by_Project does not.'
                % expected['vendor_name']
            )
        _assert_close(expected, actual, expected['vendor_name'], precision)
    recomputed_projects = {
        row['project_code']: row for row in recompute_project_totals(project_rows)
    }
    for expected in project_totals:
        actual = recomputed_projects.get(expected['project_code'])
        if not actual:
            raise UserError(
                'Project_Totals has %s but Vendor_by_Project does not.'
                % expected['project_code']
            )
        _assert_close(expected, actual, expected['project_code'], precision)


def _assert_close(expected, actual, label, precision):
    for key in ('debit', 'credit', 'balance'):
        if abs(expected[key] - actual[key]) > precision:
            raise UserError(
                'Imported %s %s does not match Vendor_by_Project (Excel %.2f vs recomputed %.2f).'
                % (label, key, expected[key], actual[key])
            )


def build_workbook(sheets):
    """Build a simple xlsx from {sheet_name: {'headers': [], 'rows': [[...]]}}."""
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    workbook_sheets = []
    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    files = {}
    for index, (name, payload) in enumerate(sheets.items(), 1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        workbook_sheets.append(f'<sheet name="{_xe(name)}" sheetId="{index}" r:id="rId{index}"/>')
        files[f'xl/worksheets/sheet{index}.xml'] = _sheet_xml(payload['headers'], payload['rows'])
    content_types.append('</Types>')
    workbook_rels.append('</Relationships>')
    files['[Content_Types].xml'] = ''.join(content_types)
    files['_rels/.rels'] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    files['xl/workbook.xml'] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>'
    )
    files['xl/_rels/workbook.xml.rels'] = ''.join(workbook_rels)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, payload in files.items():
            archive.writestr(path, payload)
    return buffer.getvalue()


def _sheet_xml(headers, rows):
    body = ['<row r="1">']
    for index, header in enumerate(headers, 1):
        body.append(
            f'<c r="{_col_letter(index)}1" t="inlineStr"><is><t>{_xe(header)}</t></is></c>'
        )
    body.append('</row>')
    for row_idx, row in enumerate(rows, 2):
        body.append(f'<row r="{row_idx}">')
        for col_idx, value in enumerate(row, 1):
            ref = f'{_col_letter(col_idx)}{row_idx}'
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                body.append(f'<c r="{ref}" t="n"><v>{float(value):.6f}</v></c>')
            else:
                body.append(f'<c r="{ref}" t="inlineStr"><is><t>{_xe(value)}</t></is></c>')
        body.append('</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def build_sample_workbook():
    """Abdul Rehman two-project fixture used by tests and empty-state demos."""
    sindhri = (53614900.0, 64585328.0, 10970428.0)
    deharki = (9300000.0, 9517897.0, 217897.0)
    nawaz = (0.0, 78.0, 78.0)
    return build_workbook({
        SHEET_VENDOR_PROJECT: {
            'headers': ['Vendor', 'Project Code', 'Project Name', 'Debit', 'Credit', 'Balance'],
            'rows': [
                ['ABDUL REHMAN CRUSH SUPPLIER', 'AG-SO-0017-24', 'SINDHRI', *sindhri],
                ['ABDUL REHMAN CRUSH SUPPLIER', 'AG-SO-0028-26', 'DEHARKI', *deharki],
                ['NAWAZ SUPPLIER', 'AG-SO-0006-24', 'PIONEER', *nawaz],
            ],
        },
        SHEET_VENDOR_ACCOUNT: {
            'headers': [
                'Vendor', 'Project Code', 'Project Name', 'Category',
                'Account Name', 'Debit', 'Credit', 'Balance',
            ],
            'rows': [
                [
                    'ABDUL REHMAN CRUSH SUPPLIER', 'AG-SO-0017-24', 'SINDHRI', '',
                    '07-01-001-0001 — CREDITOR FOR RAW MATERIAL', *sindhri,
                ],
                [
                    'ABDUL REHMAN CRUSH SUPPLIER', 'AG-SO-0028-26', 'DEHARKI', '',
                    '07-01-001-0001 — CREDITOR FOR RAW MATERIAL', *deharki,
                ],
                [
                    'NAWAZ SUPPLIER', 'AG-SO-0006-24', 'PIONEER', 'CRUSH',
                    '07-01-001-0001 — CREDITOR FOR RAW MATERIAL', *nawaz,
                ],
            ],
        },
        SHEET_VENDOR_TOTAL: {
            'headers': ['Vendor', 'Projects', 'Debit', 'Credit', 'Balance'],
            'rows': [
                ['ABDUL REHMAN CRUSH SUPPLIER', 2, 62914900.0, 74103225.0, 11188325.0],
                ['NAWAZ SUPPLIER', 1, 0.0, 78.0, 78.0],
            ],
        },
        SHEET_PROJECT_TOTAL: {
            'headers': ['Project Code', 'Project Name', 'Vendors', 'Debit', 'Credit', 'Balance'],
            'rows': [
                ['AG-SO-0017-24', 'SINDHRI', 1, *sindhri],
                ['AG-SO-0028-26', 'DEHARKI', 1, *deharki],
                ['AG-SO-0006-24', 'PIONEER', 1, *nawaz],
            ],
        },
        SHEET_CLIENT_PROJECT: {
            'headers': ['Client', 'Project Code', 'Project Name', 'Debit', 'Credit', 'Balance (Dr-Cr)'],
            'rows': [
                ['DEHARKI SUGAR MILLS', 'AG-SO-0028-26', 'DEHARKI', 2705602.0, 40354386.0, -37648784.0],
            ],
        },
        SHEET_CLIENT_ACCOUNT: {
            'headers': [
                'Client', 'Project Code', 'Project Name', 'Category',
                'Account Name', 'Debit', 'Credit', 'Balance (Dr-Cr)',
            ],
            'rows': [
                [
                    'DEHARKI SUGAR MILLS', 'AG-SO-0028-26', 'DEHARKI', '',
                    'TRADE DEBTORS LOCALS', 0.0, 8716109.0, -8716109.0,
                ],
            ],
        },
        SHEET_CLIENT_TOTAL: {
            'headers': ['Client', 'Projects', 'Debit', 'Credit', 'Overall Balance (Dr-Cr)'],
            'rows': [
                ['DEHARKI SUGAR MILLS', 1, 2705602.0, 40354386.0, -37648784.0],
            ],
        },
        SHEET_PROJECT_CLIENT_TOTAL: {
            'headers': ['Project Code', 'Project Name', 'Clients', 'Debit', 'Credit', 'Balance (Dr-Cr)'],
            'rows': [
                ['AG-SO-0028-26', 'DEHARKI', 1, 2705602.0, 40354386.0, -37648784.0],
            ],
        },
    })

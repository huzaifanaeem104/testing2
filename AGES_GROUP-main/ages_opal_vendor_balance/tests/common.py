# -*- coding: utf-8 -*-

import base64

from odoo.tests.common import TransactionCase

from odoo.addons.ages_opal_vendor_balance.report.opal_xlsx_io import build_sample_workbook


class OpalVendorBalanceCase(TransactionCase):

    def _import_sample(self):
        data = build_sample_workbook()
        record = self.env['opal.vendor.balance.import'].create({
            'data_file': base64.b64encode(data),
            'data_filename': 'opal_vendor_balance_sample.xlsx',
        })
        record._process_import()
        return record

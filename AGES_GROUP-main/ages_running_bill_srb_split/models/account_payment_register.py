# -*- coding: utf-8 -*-

from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _ages_clear_withheld_sales_tax_on_source_invoices(self):
        """No-op: AGES-SRB-WHT credit notes are no longer created."""
        return

    def _create_payments(self):
        return super()._create_payments()

# -*- coding: utf-8 -*-

from .project_cash_ledger import ProjectCashLedgerEngine


class MobilizationReportEngine(ProjectCashLedgerEngine):
    """Client mobilization cash: posted debit / credit by account."""

    special_account_fname = 'ages_mobilization_account_id'
    payment_move_link_fname = 'ages_mobilization_advance_id'
    source_model = 'ages.mobilization.advance'
    warning_label = 'mobilization'
    percent_field = 'mobilization_percent'
    percent_key = 'mobilization_percent'

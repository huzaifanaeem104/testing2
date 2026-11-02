# -*- coding: utf-8 -*-

from .project_cash_ledger import ProjectCashLedgerEngine


class RetentionReportEngine(ProjectCashLedgerEngine):
    """Client retention cash: posted debit / credit by account."""

    special_account_fname = 'ages_retention_account_id'
    payment_move_link_fname = 'ages_retention_recovery_id'
    source_model = 'ages.retention.recovery'
    warning_label = 'retention'
    percent_field = 'retention_percent'
    percent_key = 'retention_percent'

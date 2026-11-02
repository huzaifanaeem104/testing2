# -*- coding: utf-8 -*-

from . import controllers
from . import models
from . import report


def set_periodicity_journal_on_companies(env):
    for company in env['res.company'].search([]):
        if not company.account_tax_periodicity_journal_id:
            journal = company._get_default_misc_journal()
            if journal:
                company.account_tax_periodicity_journal_id = journal
                if not journal.show_on_dashboard:
                    journal.show_on_dashboard = True
        company._generate_tax_return_reminder_activity()

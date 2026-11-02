# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    account_tax_periodicity = fields.Selection(
        related='company_id.account_tax_periodicity',
        string='Periodicity',
        readonly=False,
        required=True,
    )
    account_tax_periodicity_reminder_day = fields.Integer(
        related='company_id.account_tax_periodicity_reminder_day',
        string='Reminder',
        readonly=False,
        required=True,
    )
    account_tax_periodicity_journal_id = fields.Many2one(
        related='company_id.account_tax_periodicity_journal_id',
        string='Journal',
        readonly=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        if not company.account_tax_periodicity_journal_id:
            journal = company._get_default_misc_journal()
            if journal:
                company.account_tax_periodicity_journal_id = journal
                res['account_tax_periodicity_journal_id'] = journal.id
        return res

    def open_tax_group_list(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tax groups',
            'res_model': 'account.tax.group',
            'view_mode': 'list',
            'views': [(False, 'list'), (False, 'form')],
            'context': {
                'default_country_id': self.account_fiscal_country_id.id,
                'search_default_country_id': self.account_fiscal_country_id.id,
            },
        }

from odoo import models, api, fields

from .project_directory_ledger_engine import ProjectDirectoryLedgerEngine
from .report_branding import get_ages_branding_values


class ReportProjectDirectoryLedger(models.AbstractModel):
    _name = 'report.ages_custom_reports.project_dir_ledger'
    _description = 'Project Directory Ledger Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form')
        if not form and docids:
            wizard = self.env['project.directory.ledger.wizard'].browse(docids[:1])
            if wizard.exists():
                form = {
                    'date_from': wizard.date_from,
                    'date_to': wizard.date_to,
                    'analytic_account_id': wizard.analytic_account_id.id,
                    'account_id': wizard.account_id.id,
                    'partner_id': wizard.partner_id.id,
                    'hide_account_payable': wizard.hide_account_payable,
                    'hide_cost_of_revenue': wizard.hide_cost_of_revenue,
                    'hide_bank': wizard.hide_bank,
                    'target_move': wizard.target_move,
                }
        form = form or {}

        engine = ProjectDirectoryLedgerEngine(self.env, form)
        report_data = engine.get_report_data()
        company = self.env.company
        filter_summary = ' · '.join(
            f'{label}: {value}' for label, value in report_data['filter_labels']
        )
        report_date = fields.Date.context_today(self)
        return {
            'doc_ids': docids,
            'doc_model': 'project.directory.ledger.wizard',
            'data': form,
            'grouped_data': report_data['grouped_data'],
            'line_project_names': report_data['line_project_names'],
            'running_balances': report_data['running_balances'],
            'company': company,
            'currency': company.currency_id,
            'filter_labels': report_data['filter_labels'],
            'group_by_label': report_data['group_by_label'],
            'group_by': report_data['group_by'],
            'grand_totals': report_data['grand_totals'],
            'report_date': report_date,
            'line_count': report_data['line_count'],
            'group_count': report_data['group_count'],
            **get_ages_branding_values(),
            'report_title': 'Project Directory Ledger',
            'report_subtitle': (
                f"{report_data['group_by_label']} · Generated {report_date} · "
                f"Currency: {company.currency_id.name}"
                + (f' · {filter_summary}' if filter_summary else '')
            ),
        }

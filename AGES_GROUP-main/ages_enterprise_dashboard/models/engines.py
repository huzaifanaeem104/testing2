# -*- coding: utf-8 -*-
"""Optional reuse of AGES report engines when those modules are installed."""

import importlib.util
import logging
import os
import sys

from odoo import fields, models

_logger = logging.getLogger(__name__)
_ENGINE_CACHE = {}


class AgesEnterpriseDashboardEngines(models.AbstractModel):
    _inherit = 'ages.enterprise.dashboard'

    def _engine_env(self, scope):
        company_ids = [cid for cid in (scope.get('company_ids') or []) if cid] or list(self.env.companies.ids)
        if not company_ids:
            return self.env
        return self.env(context=dict(self.env.context, allowed_company_ids=company_ids))

    def _engine_form(self, scope, extra=None):
        form = {
            'date_from': scope.get('date_from'),
            'date_to': scope.get('date_to') or fields.Date.context_today(self),
            'company_ids': [cid for cid in (scope.get('company_ids') or []) if cid],
            'sub_company_ids': [sid for sid in (scope.get('sub_company_ids') or []) if sid],
            'include_unassigned': bool(scope.get('include_unassigned')),
            'project_ids': scope.get('project_ids') or False,
            'target_move': 'posted',
            'hide_zero': True,
            'confirmed_only': True,
        }
        if extra:
            form.update(extra)
        return form

    def _load_engine_class(self, cache_key, addon_module, class_name, relative_paths):
        if cache_key in _ENGINE_CACHE:
            return _ENGINE_CACHE[cache_key]
        try:
            module = __import__(addon_module, fromlist=[class_name])
            engine_cls = getattr(module, class_name, False)
            if engine_cls:
                _ENGINE_CACHE[cache_key] = engine_cls
                return engine_cls
        except ImportError:
            pass
        here = os.path.abspath(__file__)
        module_dir = os.path.dirname(os.path.dirname(here))
        ages_group = os.path.dirname(module_dir)
        repo_root = os.path.dirname(ages_group)
        bases = (repo_root, ages_group, os.path.dirname(repo_root))
        for base in bases:
            for relative in relative_paths:
                path = os.path.normpath(os.path.join(base, relative))
                if not os.path.isfile(path):
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(
                        'ages_ent_%s' % cache_key, path
                    )
                    if not spec or not spec.loader:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    engine_cls = getattr(module, class_name, False)
                    if engine_cls:
                        _ENGINE_CACHE[cache_key] = engine_cls
                        return engine_cls
                except Exception as exc:
                    _logger.warning('Could not load %s from %s: %s', class_name, path, exc)
        _ENGINE_CACHE[cache_key] = False
        return False

    def _aged_partner_totals(self, scope, report_type):
        engine_cls = self._load_engine_class(
            'aged_partner',
            'odoo.addons.ages_custom_reports.report.aged_partner_balance_engine',
            'AgedPartnerBalanceEngine',
            ['AGES_GROUP/ages_custom_reports/report/aged_partner_balance_engine.py',
             'ages_custom_reports/report/aged_partner_balance_engine.py'],
        )
        if not engine_cls:
            return False
        if not self._can_read('account.move.line'):
            return False
        try:
            engine = engine_cls(self._engine_env(scope), {
                'report_type': report_type,
                'date_to': scope.get('date_to') or fields.Date.context_today(self),
            })
            data = engine.get_report_data()
        except Exception as exc:
            _logger.warning('Aged partner engine failed (%s): %s', report_type, exc)
            return False
        labels = data.get('period_labels') or {}
        total = next((line for line in data.get('lines') or [] if line.get('line_type') == 'total'), {})
        keys = ['period0', 'period1', 'period2', 'period3', 'period4', 'period5']
        return {
            'labels': [labels.get(key, key) for key in keys],
            'values': [round(abs(total.get(key) or 0.0), 2) for key in keys],
            'total': abs(total.get('total') or 0.0),
            'date_label': data.get('date_label') or '',
            'title': data.get('title') or report_type,
        }

    def _main_summary_payload(self, scope):
        engine_cls = self._load_engine_class(
            'main_summary',
            'odoo.addons.ages_main_summary.report.main_summary_engine',
            'MainSummaryEngine',
            ['ages_main_summary/report/main_summary_engine.py',
             'AGES_GROUP/ages_main_summary/report/main_summary_engine.py'],
        )
        if not engine_cls or not self._can_read('account.move.line'):
            return False
        try:
            return engine_cls(self._engine_env(scope), self._engine_form(scope)).get_report_data()
        except Exception as exc:
            _logger.warning('Main Summary engine failed: %s', exc)
            return False

    def _profit_loss_payload(self, scope):
        engine_cls = self._load_engine_class(
            'profit_loss',
            'odoo.addons.ages_custom_reports.report.profit_loss_engine',
            'ProfitLossEngine',
            ['AGES_GROUP/ages_custom_reports/report/profit_loss_engine.py',
             'ages_custom_reports/report/profit_loss_engine.py'],
        )
        if not engine_cls:
            return False
        if not self._can_read('account.move.line'):
            return False
        try:
            engine = engine_cls(self._engine_env(scope), self._engine_form(scope))
            data = engine.get_report_data()
            data['flat'] = engine.flatten_lines(data.get('lines') or [])
            return data
        except Exception as exc:
            _logger.warning('Profit & Loss engine failed: %s', exc)
            return False

    def _project_cash_engine_payload(self, scope, engine_cls, label):
        if not self._can_read('ages.contract') or not self._can_read('account.move.line'):
            return False
        try:
            return engine_cls(self._engine_env(scope), self._engine_form(scope)).get_report_data()
        except Exception as exc:
            _logger.warning('%s engine failed: %s', label, exc)
            return False

    def _mobilization_engine_payload(self, scope):
        engine_cls = self._load_engine_class(
            'mobilization',
            'odoo.addons.ages_project_reporting.report.mobilization_report_engine',
            'MobilizationReportEngine',
            ['AGES_GROUP/ages_project_reporting/report/mobilization_report_engine.py',
             'ages_project_reporting/report/mobilization_report_engine.py'],
        )
        if not engine_cls:
            return False
        return self._project_cash_engine_payload(scope, engine_cls, 'Mobilization')

    def _retention_engine_payload(self, scope):
        engine_cls = self._load_engine_class(
            'retention',
            'odoo.addons.ages_project_reporting.report.retention_report_engine',
            'RetentionReportEngine',
            ['AGES_GROUP/ages_project_reporting/report/retention_report_engine.py',
             'ages_project_reporting/report/retention_report_engine.py'],
        )
        if not engine_cls:
            return False
        return self._project_cash_engine_payload(scope, engine_cls, 'Retention')

    def _engine_total_line(self, payload):
        if not payload:
            return {}
        return next(
            (line for line in payload.get('lines') or [] if line.get('line_type') == 'total'),
            {},
        )

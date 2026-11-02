# -*- coding: utf-8 -*-
import logging

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

ROOT_VIEW_TAGS = ('form', 'list', 'tree', 'kanban')
NESTED_VIEW_TAGS = ('form', 'list', 'tree', 'kanban')


class BaseButtonAccess(models.AbstractModel):
    _inherit = 'base'

    def _button_access_rule_model(self):
        if 'button.access.rule' not in self.env:
            return None
        return self.env['button.access.rule'].sudo()

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result:
            return result
        if self.env.su or self.env.uid == 1 or self.env.context.get('button_access_skip'):
            return None
        if 'access.profile' not in self.env:
            return None
        try:
            denied = self.env['access.profile']._operation_denied(self._name, operation)
        except Exception:
            _logger.exception(
                'button_access_manager: profile ACL check failed for %s %s',
                self._name, operation)
            return None
        if denied:
            def _make_error():
                return AccessError(_(
                    "This action has been restricted for your user account. "
                    "Please contact your administrator if you believe this is a mistake."
                ))
            return self, _make_error
        return None

    @api.model_create_multi
    def create(self, vals_list):
        Rule = self._button_access_rule_model()
        if Rule is not None:
            Rule.enforce(self._name, 'create')
        return super().create(vals_list)

    def unlink(self):
        Rule = self._button_access_rule_model()
        if Rule is not None and self:
            Rule.enforce(self._name, 'delete')
        return super().unlink()

    def copy(self, default=None):
        Rule = self._button_access_rule_model()
        if Rule is not None:
            Rule.enforce(self._name, 'duplicate')
        return super().copy(default)

    def action_archive(self):
        Rule = self._button_access_rule_model()
        if Rule is not None:
            Rule.enforce(self._name, 'object', 'action_archive')
        return super().action_archive()

    def action_unarchive(self):
        Rule = self._button_access_rule_model()
        if Rule is not None:
            Rule.enforce(self._name, 'object', 'action_unarchive')
        return super().action_unarchive()

    def toggle_active(self):
        Rule = self._button_access_rule_model()
        if Rule is not None:
            Rule.enforce(self._name, 'object', 'toggle_active')
        return super().toggle_active()

    def export_data(self, fields_to_export):
        Rule = self._button_access_rule_model()
        if Rule is not None:
            Rule.enforce(self._name, 'export')
        return super().export_data(fields_to_export)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id, view_type, **options)
        if self.env.context.get('button_access_skip') or self.env.uid == 1:
            return result
        Rule = self._button_access_rule_model()
        if Rule is None:
            return result
        rules = Rule.rules_for_model(self._name)
        if not rules:
            return result
        arch = result.get('arch')
        if not arch:
            return result
        try:
            root = etree.fromstring(arch.encode('utf-8') if isinstance(arch, str) else arch)
        except Exception:
            _logger.exception('button_access_manager: could not parse view arch for %s', self._name)
            return result
        self._button_access_apply_arch(root, rules, self._name)
        result['arch'] = etree.tostring(root, encoding='unicode')
        return result

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options=options)
        if self.env.context.get('button_access_skip') or self.env.uid == 1:
            return result
        Rule = self._button_access_rule_model()
        if Rule is None:
            return result
        rules = Rule.rules_for_model(self._name)
        if not rules:
            return result
        blocked_action_names = set()
        hide_all_reports = False
        hide_all_actions = False
        for rule in rules:
            if rule['type'] == 'report':
                if not rule['name']:
                    hide_all_reports = True
                else:
                    blocked_action_names.add(str(rule['name']))
            elif rule['type'] == 'action':
                if not rule['name']:
                    hide_all_actions = True
                else:
                    blocked_action_names.add(str(rule['name']))
        views_dict = result.get('views') or {}
        for view in views_dict.values():
            toolbar = view.get('toolbar') or {}
            if hide_all_reports:
                toolbar['print'] = []
            elif toolbar.get('print'):
                toolbar['print'] = [
                    act for act in toolbar['print']
                    if not self._button_access_toolbar_match(act, blocked_action_names)
                ]
            if hide_all_actions:
                toolbar['action'] = [
                    act for act in (toolbar.get('action') or [])
                    if act.get('callback')
                ]
            elif toolbar.get('action') and blocked_action_names:
                toolbar['action'] = [
                    act for act in toolbar['action']
                    if act.get('callback') or not self._button_access_toolbar_match(act, blocked_action_names)
                ]
        return result

    def _button_access_toolbar_match(self, action, blocked_names):
        if not blocked_names:
            return False
        xmlid = action.get('xml_id') or action.get('xmlid') or ''
        action_id = str(action.get('id') or '')
        path = action.get('path') or ''
        return action_id in blocked_names or xmlid in blocked_names or (path and path in blocked_names)

    def _button_access_apply_arch(self, root, rules, model_name):
        if root.tag in ROOT_VIEW_TAGS:
            self._button_access_apply_root_attrs(root, rules)
        self._button_access_strip_buttons(root, rules)
        self._button_access_apply_nested(root, model_name)

    def _button_access_apply_root_attrs(self, root, rules):
        types = {rule['type'] for rule in rules}
        if 'create' in types:
            root.set('create', 'false')
        if 'delete' in types:
            root.set('delete', 'false')
        if 'duplicate' in types:
            root.set('duplicate', 'false')
        if 'import' in types:
            root.set('import', 'false')
        if 'export' in types:
            root.set('export_xlsx', 'false')
            root.set('export', 'false')

    def _button_access_strip_buttons(self, root, rules):
        names = {
            str(rule['name'])
            for rule in rules
            if rule['type'] in ('object', 'action', 'report', 'other') and rule['name']
        }
        if not names:
            return
        for button in root.xpath('.//button[@name]'):
            if button.get('name') in names:
                parent = button.getparent()
                if parent is not None:
                    parent.remove(button)
        for anchor in root.xpath('.//a[@name]'):
            if anchor.get('name') in names:
                parent = anchor.getparent()
                if parent is not None:
                    parent.remove(anchor)

    def _button_access_apply_nested(self, root, model_name):
        if model_name not in self.env:
            return
        Model = self.env[model_name]
        Rule = self._button_access_rule_model()
        for field_el in root.xpath('.//field[@name]'):
            field = Model._fields.get(field_el.get('name'))
            if not field or field.type not in ('one2many', 'many2many') or not field.comodel_name:
                continue
            nested_rules = Rule.rules_for_model(field.comodel_name)
            if not nested_rules:
                continue
            for child in field_el:
                if child.tag in NESTED_VIEW_TAGS:
                    self._button_access_apply_root_attrs(child, nested_rules)
                    self._button_access_strip_buttons(child, nested_rules)

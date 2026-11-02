# -*- coding: utf-8 -*-
import logging

from odoo import fields, models, _
from odoo.exceptions import UserError

from odoo.addons.button_access_manager.models.constants import BUTTON_TYPE_SELECTION

_logger = logging.getLogger(__name__)

try:
    from lxml import etree
except ImportError:  # pragma: no cover
    etree = None

STANDARD_ENTRIES = [
    ('create', '', 'New', 'list, form'),
    ('delete', '', 'Delete', 'list, form (cog menu)'),
    ('duplicate', '', 'Duplicate', 'form (cog menu)'),
    ('import', '', 'Import', 'list (cog menu)'),
    ('export', '', 'Export', 'list (cog menu)'),
    ('object', 'action_archive', 'Archive', 'list, form (cog menu)'),
    ('object', 'action_unarchive', 'Unarchive', 'list, form (cog menu)'),
    ('report', '', 'Print (all reports)', 'print menu'),
]

SCANNABLE_VIEW_TYPES = ['list', 'form', 'kanban']
NESTED_VIEW_TAGS = ('form', 'list', 'tree', 'kanban')


class ButtonAccessScanWizard(models.TransientModel):
    _name = 'button.access.scan.wizard'
    _description = 'Scan & Hide Buttons Wizard'

    model_id = fields.Many2one('ir.model', string='Model', required=True)
    user_ids = fields.Many2many(
        'res.users', string='Hide From Users',
        help='The buttons you select below will be hidden and blocked for these users.')
    group_ids = fields.Many2many(
        'res.groups', string='Hide From Groups',
        help='The buttons you select below will be hidden and blocked for these groups.')
    line_ids = fields.One2many('button.access.scan.line', 'wizard_id', string='Buttons Found')
    scanned = fields.Boolean(default=False)

    def _target_ok(self):
        return bool(self.user_ids or self.group_ids)

    def _add_found(self, found, model_id, button_type, tname, label, views):
        key = (model_id, button_type, tname or '')
        if key in found:
            existing_views = found[key]['view_types'] or ''
            extra = views or ''
            for part in extra.split(','):
                part = part.strip()
                if part and part not in existing_views:
                    found[key]['view_types'] = (existing_views + ', ' + part).strip(', ')
        else:
            found[key] = {
                'line_model_id': model_id,
                'button_type': button_type,
                'technical_name': tname or '',
                'button_string': label,
                'view_types': views or '',
                'selected': False,
            }

    def _scan_element(self, element, model_name, vtype, found):
        if model_name not in self.env:
            return
        IrModel = self.env['ir.model'].sudo()
        model_rec = IrModel._get(model_name)
        model_id = model_rec.id if model_rec else False
        if not model_id:
            return
        for button in element.xpath('./button | .//button[not(ancestor::field)]'):
            name = (button.get('name') or '').strip()
            btn_type_attr = (button.get('type') or '').strip()
            string = (button.get('string') or name or '').strip()
            if btn_type_attr == 'object' and name:
                self._add_found(found, model_id, 'object', name, string, vtype)
            elif btn_type_attr == 'action' and name:
                self._add_found(found, model_id, 'action', name, string, vtype)
        Model = self.env[model_name]
        for field_el in element.xpath('.//field[@name][not(ancestor::field)]'):
            field = Model._fields.get(field_el.get('name'))
            if not field or field.type not in ('one2many', 'many2many') or not field.comodel_name:
                continue
            for child in field_el:
                if child.tag in NESTED_VIEW_TAGS:
                    nested_type = 'list' if child.tag == 'tree' else child.tag
                    self._scan_element(
                        child, field.comodel_name, '%s/%s' % (vtype, field.comodel_name), found)

    def _scan_reports(self, model_name, found):
        IrModel = self.env['ir.model'].sudo()
        model_rec = IrModel._get(model_name)
        if not model_rec:
            return
        try:
            bindings = self.env['ir.actions.actions'].sudo().get_bindings(model_name)
        except Exception:
            _logger.exception(
                'button_access_manager: could not load action bindings for %s', model_name)
            return
        for action in bindings.get('report') or []:
            action_id = str(action.get('id') or '')
            xmlid = action.get('xml_id') or action.get('xmlid') or action_id
            label = action.get('name') or action.get('display_name') or 'Print'
            self._add_found(
                found, model_rec.id, 'report', xmlid or action_id, label, 'print menu')
        for action in bindings.get('action') or []:
            action_id = str(action.get('id') or '')
            xmlid = action.get('xml_id') or action.get('xmlid') or action_id
            label = action.get('name') or action.get('display_name') or 'Action'
            if xmlid or action_id:
                self._add_found(
                    found, model_rec.id, 'action', xmlid or action_id, label, 'action menu')

    def _pretick(self, found):
        Rule = self.env['button.access.rule'].sudo()
        user_ids = set(self.user_ids.ids)
        group_ids = set(self.group_ids.ids)
        if not user_ids and not group_ids:
            return
        for key, vals in found.items():
            model_id, button_type, tname = key
            domain = [
                ('model_id', '=', model_id),
                ('button_type', '=', button_type),
                ('technical_name', '=', tname or ''),
                ('active', '=', True),
            ]
            rules = Rule.search(domain)
            if not rules:
                continue
            if user_ids:
                covered_users = set(rules.mapped('user_ids').ids)
                if not user_ids <= covered_users:
                    # also count group membership of the selected users
                    covered_groups = set(rules.mapped('group_ids').ids)
                    users = self.env['res.users'].sudo().browse(list(user_ids))
                    missing = [
                        user.id for user in users
                        if user.id not in covered_users
                        and not (set(user.groups_id.ids) & covered_groups)
                    ]
                    if missing:
                        continue
            if group_ids:
                covered_groups = set(rules.mapped('group_ids').ids)
                if not group_ids <= covered_groups:
                    continue
            vals['selected'] = True

    def action_scan(self):
        self.ensure_one()
        if not self._target_ok():
            raise UserError(_('Select at least one user or group to hide buttons from.'))
        self.line_ids.unlink()
        model_name = self.model_id.model
        found = {}
        for btype, tname, label, views in STANDARD_ENTRIES:
            self._add_found(found, self.model_id.id, btype, tname, label, views)

        if etree is not None and model_name in self.env:
            Model = self.env[model_name].sudo().with_context(button_access_skip=True)
            for vtype in SCANNABLE_VIEW_TYPES:
                try:
                    res = Model.get_view(view_type=vtype)
                    arch = res.get('arch')
                    if not arch:
                        continue
                    root = etree.fromstring(arch.encode('utf-8') if isinstance(arch, str) else arch)
                    self._scan_element(root, model_name, vtype, found)
                except Exception:
                    _logger.exception(
                        'button_access_manager: could not scan %s view for model %s',
                        vtype, model_name)
                    continue
            self._scan_reports(model_name, found)

        self._pretick(found)
        lines = [(0, 0, vals) for vals in found.values()]
        self.write({'line_ids': lines, 'scanned': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        self.ensure_one()
        if not self._target_ok():
            raise UserError(_('Select at least one user or group to hide buttons from.'))
        Rule = self.env['button.access.rule']
        for line in self.line_ids.filtered('selected'):
            Rule._create_or_update_rule(
                model_id=line.line_model_id.id or self.model_id.id,
                button_type=line.button_type,
                technical_name=line.technical_name,
                button_string=line.button_string,
                view_types=line.view_types,
                user_ids=self.user_ids.ids,
                group_ids=self.group_ids.ids,
            )
        return {'type': 'ir.actions.act_window_close'}


class ButtonAccessScanLine(models.TransientModel):
    _name = 'button.access.scan.line'
    _description = 'Discovered Button Line'

    wizard_id = fields.Many2one('button.access.scan.wizard', ondelete='cascade')
    selected = fields.Boolean(string='Hide?')
    line_model_id = fields.Many2one('ir.model', string='Model', readonly=True)
    button_type = fields.Selection(BUTTON_TYPE_SELECTION, readonly=True)
    technical_name = fields.Char(readonly=True)
    button_string = fields.Char(readonly=True, string='Label')
    view_types = fields.Char(readonly=True, string='Found In')

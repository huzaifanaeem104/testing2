# -*- coding: utf-8 -*-

import json
import logging

from odoo import api, fields, models
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.exceptions import UserError
from odoo.models import NewId
from odoo.tools.translate import _

from .constants import (
    BUSINESS_MODULE_SELECTION,
    DELETION_SOURCE_SELECTION,
    DELETION_TYPE_SELECTION,
    EXCLUDED_MODEL_PREFIXES,
    EXCLUDED_NAME_FRAGMENTS,
    MODEL_PREFIX_AREA,
    MODULE_PREFIX_AREA,
    MODULE_TO_AREA,
    PARAM_ENABLED,
    PRIORITY_FIELDS,
    SENSITIVE_FIELD_NAMES,
    SENSITIVE_NAME_PARTS,
    SKIP_FIELD_TYPES,
    SKIP_RELATIONAL_SNAPSHOT,
    SNAPSHOT_FIELD_LIMIT,
    SNAPSHOT_REL_LIMIT,
    SNAPSHOT_TEXT_LIMIT,
)

_logger = logging.getLogger(__name__)


def _is_real_id(record_id):
    return bool(record_id) and not isinstance(record_id, NewId) and isinstance(record_id, int)


class AgesDeletionAudit(models.Model):
    _name = 'ages.deletion.audit'
    _description = 'Deleted Record'
    _order = 'deletion_date desc, id desc'
    _rec_name = 'display_label'

    display_label = fields.Char(
        string='Summary',
        compute='_compute_display_label',
        store=True,
    )
    business_module = fields.Selection(
        selection=BUSINESS_MODULE_SELECTION,
        string='Business Module',
        required=True,
        index=True,
        readonly=True,
    )
    model_name = fields.Char(
        string='Model',
        required=True,
        index=True,
        readonly=True,
    )
    model_description = fields.Char(
        string='Model Display Name',
        readonly=True,
    )
    record_id = fields.Integer(
        string='Original Record ID',
        required=True,
        index=True,
        readonly=True,
    )
    record_name = fields.Char(
        string='Original Record Name',
        readonly=True,
        index=True,
    )
    deleted_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Deleted By',
        index=True,
        readonly=True,
        ondelete='set null',
    )
    deleted_by_uid = fields.Integer(
        string='Deleted User ID',
        readonly=True,
        index=True,
    )
    deleted_by_name = fields.Char(
        string='Deleted By Name',
        readonly=True,
    )
    deletion_date = fields.Datetime(
        string='Deleted On',
        required=True,
        index=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        index=True,
        readonly=True,
        ondelete='set null',
    )
    company_name = fields.Char(
        string='Company Name',
        readonly=True,
    )
    original_create_uid = fields.Integer(
        string='Original Creator ID',
        readonly=True,
    )
    original_create_name = fields.Char(
        string='Original Creator',
        readonly=True,
    )
    original_create_date = fields.Datetime(
        string='Original Created On',
        readonly=True,
    )
    deletion_source = fields.Selection(
        selection=DELETION_SOURCE_SELECTION,
        string='Deletion Source',
        required=True,
        default='unknown',
        index=True,
        readonly=True,
    )
    deletion_type = fields.Selection(
        selection=DELETION_TYPE_SELECTION,
        string='Deletion Type',
        required=True,
        default='user_initiated',
        index=True,
        readonly=True,
    )
    parent_model = fields.Char(
        string='Related Parent Model',
        readonly=True,
    )
    parent_record_ids = fields.Char(
        string='Related Parent IDs',
        readonly=True,
    )
    snapshot_summary = fields.Char(
        string='Snapshot Summary',
        readonly=True,
    )
    snapshot = fields.Text(
        string='Pre-Deletion Snapshot',
        readonly=True,
    )

    @api.depends('model_name', 'record_id', 'record_name')
    def _compute_display_label(self):
        for rec in self:
            name = rec.record_name or ''
            rec.display_label = '%s #%s%s' % (
                rec.model_name or '',
                rec.record_id or '',
                (' — %s' % name) if name else '',
            )

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ages_deletion_audit_model_record_idx
            ON ages_deletion_audit (model_name, record_id)
        """)
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS ages_deletion_audit_module_date_idx
            ON ages_deletion_audit (business_module, deletion_date DESC)
        """)

    def write(self, vals):
        if not self.env.context.get('ages_deletion_audit_allow_write'):
            raise UserError(_('Deletion audit records cannot be modified.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('ages_deletion_audit_purge'):
            raise UserError(_('Deletion audit records cannot be deleted.'))
        return super().unlink()

    def _register_hook(self):
        res = super()._register_hook()
        self._ages_patch_unlinks()
        return res

    def _ages_patch_unlinks(self):
        registry = self.env.registry
        if getattr(registry, '_ages_deletion_audit_patched', False):
            return
        for model_name in list(registry.models):
            Model = registry[model_name]
            if Model._abstract or Model._transient:
                continue
            existing = Model.__dict__.get('unlink')
            if existing and getattr(existing, '_ages_deletion_audit', False):
                continue
            original = Model.unlink

            def unlink(self, _original=original):
                if (
                    self
                    and self._ids
                    and not self.env.context.get('ages_deletion_audit_skip')
                    and not self.env.context.get(MODULE_UNINSTALL_FLAG)
                    and not self.env.context.get('install_mode')
                ):
                    Audit = self.env.get('ages.deletion.audit')
                    if Audit is not None:
                        # Savepoint: a failed capture must not abort the whole
                        # delete transaction (psycopg2 InFailedSqlTransaction).
                        try:
                            with self.env.cr.savepoint():
                                Audit._ages_capture_unlink(self)
                        except Exception:
                            _logger.exception(
                                'ages_deletion_audit: capture failed for %s',
                                self._name,
                            )
                depth = self.env.context.get('ages_deletion_audit_depth', 0)
                parent = False
                if self and self.ids:
                    parent = '%s:%s' % (
                        self._name,
                        ','.join(str(i) for i in self.ids[:40]),
                    )
                return _original(self.with_context(
                    ages_deletion_audit_depth=depth + 1,
                    ages_deletion_parent=parent or self.env.context.get('ages_deletion_parent'),
                ))

            unlink._ages_deletion_audit = True
            unlink.__name__ = getattr(original, '__name__', 'unlink')
            unlink.__doc__ = getattr(original, '__doc__', None)
            Model.unlink = unlink
        registry._ages_deletion_audit_patched = True

    @api.model
    def _ages_audit_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_ENABLED, 'True'
        ) not in ('False', 'false', '0', '')

    @api.model
    def _ages_clear_area_cache(self):
        self.env.registry._ages_deletion_area_cache = {}
        self.env.registry._ages_deletion_exc_cache = None

    @api.model
    def _ages_exception_map(self):
        cache = getattr(self.env.registry, '_ages_deletion_exc_cache', None)
        if cache is None:
            cache = {}
            if 'ages.deletion.audit.exception' in self.env:
                for rec in self.env['ages.deletion.audit.exception'].sudo().search([]):
                    cache[rec.model_name] = (rec.action, rec.business_module)
            self.env.registry._ages_deletion_exc_cache = cache
        return cache

    @api.model
    def _ages_classify(self, model_name):
        if not model_name or model_name not in self.env:
            return False
        exception = self._ages_exception_map().get(model_name)
        if exception:
            action, module = exception
            if action == 'exclude':
                return False
            if action == 'include' and module:
                return module
        cache = getattr(self.env.registry, '_ages_deletion_area_cache', None)
        if cache is None:
            cache = {}
            self.env.registry._ages_deletion_area_cache = cache
        if model_name in cache:
            return cache[model_name]
        area = self._ages_compute_area(model_name)
        cache[model_name] = area
        return area

    @api.model
    def _ages_compute_area(self, model_name):
        Model = self.env[model_name]
        if Model._abstract or Model._transient or not Model._auto:
            return False
        lowered = model_name.lower()
        if any(lowered.startswith(prefix) for prefix in EXCLUDED_MODEL_PREFIXES):
            return False
        if any(fragment in lowered for fragment in EXCLUDED_NAME_FRAGMENTS):
            return False
        original_module = getattr(Model, '_original_module', None) or ''
        area = self._ages_area_for_module(original_module)
        if area:
            return area
        for prefix, mapped in MODEL_PREFIX_AREA:
            if model_name == prefix or model_name.startswith(prefix):
                return mapped
        return False

    @api.model
    def _ages_area_for_module(self, module_name):
        if not module_name:
            return False
        if module_name in MODULE_TO_AREA:
            return MODULE_TO_AREA[module_name]
        for prefix, area in MODULE_PREFIX_AREA:
            if module_name.startswith(prefix):
                return area
        return False

    @api.model
    def _ages_capture_unlink(self, records):
        if not records or not self._ages_audit_enabled():
            return
        if records._name == self._name or records._name.startswith('ages.deletion.audit'):
            return
        area = self._ages_classify(records._name)
        if not area:
            return
        real_records = records.browse([
            rid for rid in records._ids if _is_real_id(rid)
        ])
        if not real_records:
            return

        depth = records.env.context.get('ages_deletion_audit_depth', 0)
        deletion_type = 'user_initiated' if not depth else 'cascade'
        parent_ref = records.env.context.get('ages_deletion_parent') or ''
        parent_model = False
        parent_ids = False
        if deletion_type == 'cascade' and parent_ref and ':' in parent_ref:
            parent_model, parent_ids = parent_ref.split(':', 1)
        user = records.env.user
        source = self._ages_deletion_source(records)
        now = fields.Datetime.now()
        model_description = records._description or records._name
        snapshots = self._ages_snapshots(real_records)

        vals_list = []
        for record in real_records:
            data = snapshots.get(record.id) or {}
            company = False
            if 'company_id' in record._fields:
                try:
                    company = record.company_id
                except Exception:
                    company = False
            if not company and 'company_ids' in record._fields:
                try:
                    company = record.company_ids[:1]
                except Exception:
                    company = False
            vals_list.append({
                'business_module': area,
                'model_name': records._name,
                'model_description': model_description,
                'record_id': record.id,
                'record_name': data.get('_display_name') or self._ages_safe_display_name(record),
                'deleted_by_id': user.id,
                'deleted_by_uid': user.id,
                'deleted_by_name': user.display_name,
                'deletion_date': now,
                'company_id': company.id if company else False,
                'company_name': company.display_name if company else False,
                'original_create_uid': data.get('_create_uid') or False,
                'original_create_name': data.get('_create_name') or False,
                'original_create_date': data.get('_create_date') or False,
                'deletion_source': source,
                'deletion_type': deletion_type,
                'parent_model': parent_model,
                'parent_record_ids': parent_ids,
                'snapshot_summary': data.get('_summary') or False,
                'snapshot': data.get('_json') or '{}',
            })
        if vals_list:
            self.sudo().with_context(ages_deletion_audit_skip=True).create(vals_list)

    @api.model
    def _ages_deletion_source(self, records):
        ctx = records.env.context
        if ctx.get('import_file') or ctx.get('import_skip_records'):
            return 'import'
        if ctx.get('cron_id') or ctx.get('_job') or ctx.get('job_uuid'):
            return 'scheduled'
        try:
            from odoo.http import request
            httprequest = getattr(request, 'httprequest', None)
            path = (getattr(httprequest, 'path', None) or '') if httprequest is not None else ''
            if path:
                lowered = path.lower()
                if 'xmlrpc' in lowered or 'jsonrpc' in lowered:
                    return 'api'
                return 'ui'
        except Exception:
            pass
        return 'unknown'

    @api.model
    def _ages_safe_display_name(self, record):
        try:
            return record.display_name or str(record.id)
        except Exception:
            return str(record.id)

    @api.model
    def _ages_snapshots(self, records):
        result = {}
        field_names = self._ages_snapshot_field_names(records)
        try:
            rows = records.read(field_names, load='_classic_read')
        except Exception:
            _logger.debug(
                'ages_deletion_audit: batch read failed for %s, reading per record',
                records._name, exc_info=True,
            )
            rows = []
            for record in records:
                try:
                    rows.extend(record.read(field_names, load='_classic_read'))
                except Exception:
                    rows.append({'id': record.id})
        by_id = {row['id']: row for row in rows}
        for record in records:
            row = by_id.get(record.id) or {'id': record.id}
            result[record.id] = self._ages_format_snapshot(record, row)
        return result

    @api.model
    def _ages_snapshot_field_names(self, records):
        names = []
        seen = set()
        for fname in PRIORITY_FIELDS:
            if fname in records._fields and fname not in seen:
                field = records._fields[fname]
                if self._ages_include_field(field):
                    names.append(fname)
                    seen.add(fname)
        for fname, field in records._fields.items():
            if fname in seen:
                continue
            if len(names) >= SNAPSHOT_FIELD_LIMIT:
                break
            if self._ages_include_field(field):
                names.append(fname)
                seen.add(fname)
        for extra in ('display_name', 'create_uid', 'create_date', 'write_uid', 'write_date'):
            if extra in records._fields and extra not in seen:
                names.append(extra)
        return names

    @api.model
    def _ages_include_field(self, field):
        fname = field.name
        if fname in SKIP_RELATIONAL_SNAPSHOT:
            return False
        if fname.startswith('_'):
            return False
        if field.type in SKIP_FIELD_TYPES:
            return False
        if getattr(field, 'password', False):
            return False
        if fname in SENSITIVE_FIELD_NAMES:
            return False
        lowered = fname.lower()
        if any(part in lowered for part in SENSITIVE_NAME_PARTS):
            return False
        if fname.startswith('private_'):
            return False
        if not field.store and field.type not in ('many2one',):
            if field.compute and not field.store:
                return False
        if field.type in ('one2many', 'many2many', 'many2one', 'reference'):
            return True
        return bool(field.store or fname in ('display_name',))

    @api.model
    def _ages_format_snapshot(self, record, row):
        payload = {}
        display = row.get('display_name') or self._ages_safe_display_name(record)
        create_uid = False
        create_name = False
        create_date = row.get('create_date') or False
        create_val = row.get('create_uid')
        if isinstance(create_val, (list, tuple)) and create_val:
            create_uid = create_val[0]
            create_name = create_val[1]
        elif isinstance(create_val, int):
            create_uid = create_val

        for fname, value in row.items():
            if fname == 'id':
                payload['id'] = value
                continue
            field = record._fields.get(fname)
            if not field:
                continue
            label = field.string or fname
            payload[label] = self._ages_format_value(record, field, value)

        summary_parts = [display]
        for key in ('State', 'Status', 'Total', 'Amount', 'Partner', 'Customer', 'Vendor', 'Employee'):
            if key in payload and payload[key] not in (False, None, '', []):
                summary_parts.append('%s: %s' % (key, self._ages_summary_text(payload[key])))
        summary = ' · '.join(str(part) for part in summary_parts if part)[:250]
        return {
            '_display_name': display,
            '_create_uid': create_uid,
            '_create_name': create_name,
            '_create_date': create_date,
            '_summary': summary,
            '_json': json.dumps(payload, default=str, ensure_ascii=False, indent=2),
        }

    @api.model
    def _ages_format_value(self, record, field, value):
        if value in (False, None):
            return False
        if field.type in ('char', 'text', 'selection'):
            text = value if isinstance(value, str) else str(value)
            if len(text) > SNAPSHOT_TEXT_LIMIT:
                return text[:SNAPSHOT_TEXT_LIMIT] + '…'
            return text
        if field.type == 'many2one':
            if isinstance(value, (list, tuple)) and value:
                return {'id': value[0], 'name': value[1] if len(value) > 1 else value[0]}
            if isinstance(value, int):
                related = record.env[field.comodel_name].browse(value)
                return {'id': value, 'name': related.exists().display_name or value}
            return value
        if field.type in ('many2many', 'one2many'):
            ids = list(value or [])
            names = []
            if field.comodel_name in record.env and ids:
                related = record.env[field.comodel_name].browse(ids[:SNAPSHOT_REL_LIMIT]).exists()
                try:
                    names = related.mapped('display_name')
                except Exception:
                    names = [str(rid) for rid in related.ids]
            return {
                'count': len(ids),
                'records': [
                    {'id': rid, 'name': names[idx] if idx < len(names) else rid}
                    for idx, rid in enumerate(ids[:SNAPSHOT_REL_LIMIT])
                ],
            }
        if field.type == 'reference' and isinstance(value, str) and ',' in value:
            ref_model, ref_id = value.split(',', 1)
            name = value
            try:
                if ref_model in record.env:
                    name = record.env[ref_model].browse(int(ref_id)).display_name or value
            except Exception:
                name = value
            return {'id': value, 'name': name}
        if field.type in ('datetime', 'date'):
            return str(value) if value else False
        return value

    @api.model
    def _ages_summary_text(self, value):
        if isinstance(value, dict):
            if 'name' in value:
                return value['name']
            if 'records' in value:
                return '%s record(s)' % value.get('count', len(value['records']))
            return json.dumps(value, default=str)
        return value

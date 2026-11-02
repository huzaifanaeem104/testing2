# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .constants import BUTTON_TYPE_SELECTION, is_framework_model

_logger = logging.getLogger(__name__)


class ButtonAccessRule(models.Model):
    _name = 'button.access.rule'
    _description = 'Button Access Rule'
    _rec_name = 'display_name'
    _order = 'model_name, button_type, button_string'

    # model_id is intentionally NOT required: a blank model_id means the
    # rule applies to this button_type/technical_name on EVERY model at
    # once (used by the "Quick Global Restrictions" checkboxes).
    model_id = fields.Many2one(
        'ir.model', string='Model (leave empty = ALL models)', ondelete='cascade', index=True,
        help='The model this button belongs to. Leave empty to apply this rule '
             'to every model at once.')
    model_name = fields.Char(
        related='model_id.model', store=True, readonly=True, index=True,
        string='Technical Model')
    is_global = fields.Boolean(
        compute='_compute_is_global', store=True,
        help='True when this rule has no specific model and applies everywhere.')
    button_type = fields.Selection(
        BUTTON_TYPE_SELECTION, required=True, default='other', string='Button Type')
    technical_name = fields.Char(
        string='Technical Name / Method', default='',
        help="For 'Object Button' rules: the method name called by the button "
             "(e.g. action_confirm, action_cancel). For 'Action Button' / Print "
             "rules: the action id or xml id. Leave empty for New / Delete / "
             "Duplicate / Import / Export / all-reports.")
    button_string = fields.Char(
        string='Button Label',
        help='Admin reference. Visual hiding matches technical names and view '
             'attributes, not this translated label.')
    view_types = fields.Char(
        string='Found In Views',
        help='Informational only: which view types this button was detected in.')
    user_ids = fields.Many2many(
        'res.users', 'button_access_rule_users_rel', 'rule_id', 'user_id',
        string='Hide From Users',
        help='Hidden and blocked for these users. Combined with Hide From Groups.')
    group_ids = fields.Many2many(
        'res.groups', 'button_access_rule_groups_rel', 'rule_id', 'group_id',
        string='Hide From Groups',
        help='Hidden and blocked for every user in these groups.')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')
    uniq_key = fields.Char(
        compute='_compute_uniq_key', store=True, index=True, string='Unique Key')

    display_name = fields.Char(compute='_compute_display_name', store=False)

    _sql_constraints = [
        ('uniq_key', 'unique(uniq_key)',
         'A rule for this exact model / button type / technical name already '
         'exists. Please edit the existing rule and add the extra user(s) or '
         'group(s) to it instead of creating a duplicate.'),
    ]

    def _auto_init(self):
        cr = self.env.cr
        cr.execute(
            "ALTER TABLE IF EXISTS button_access_rule "
            "DROP CONSTRAINT IF EXISTS button_access_rule_uniq_rule"
        )
        cr.execute(
            "ALTER TABLE IF EXISTS button_access_rule "
            "DROP CONSTRAINT IF EXISTS button_access_rule_uniq_key"
        )
        self._merge_duplicate_rules()
        super()._auto_init()

    def _merge_duplicate_rules(self):
        """Collapse duplicate (model, type, name) rows left from NULL unique."""
        cr = self.env.cr
        cr.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'button_access_rule'
        """)
        if not cr.fetchone():
            return
        cr.execute("""
            SELECT COALESCE(model_id, 0), button_type, COALESCE(technical_name, ''),
                   array_agg(id ORDER BY id)
            FROM button_access_rule
            GROUP BY 1, 2, 3
            HAVING count(*) > 1
        """)
        rows = cr.fetchall()
        cr.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'button_access_rule_groups_rel'
        """)
        has_groups = bool(cr.fetchone())
        for _model, _btype, _name, ids in rows:
            keep, dupes = ids[0], ids[1:]
            if not dupes:
                continue
            cr.execute("""
                INSERT INTO button_access_rule_users_rel (rule_id, user_id)
                SELECT DISTINCT %s, user_id FROM button_access_rule_users_rel
                WHERE rule_id = ANY(%s)
                  AND user_id NOT IN (
                      SELECT user_id FROM button_access_rule_users_rel WHERE rule_id = %s
                  )
            """, (keep, dupes, keep))
            cr.execute(
                "DELETE FROM button_access_rule_users_rel WHERE rule_id = ANY(%s)",
                (dupes,),
            )
            if has_groups:
                cr.execute("""
                    INSERT INTO button_access_rule_groups_rel (rule_id, group_id)
                    SELECT DISTINCT %s, group_id FROM button_access_rule_groups_rel
                    WHERE rule_id = ANY(%s)
                      AND group_id NOT IN (
                          SELECT group_id FROM button_access_rule_groups_rel WHERE rule_id = %s
                      )
                """, (keep, dupes, keep))
                cr.execute(
                    "DELETE FROM button_access_rule_groups_rel WHERE rule_id = ANY(%s)",
                    (dupes,),
                )
            cr.execute("DELETE FROM button_access_rule WHERE id = ANY(%s)", (dupes,))

    @api.depends('model_id')
    def _compute_is_global(self):
        for rec in self:
            rec.is_global = not rec.model_id

    @api.depends('model_id', 'button_type', 'technical_name')
    def _compute_uniq_key(self):
        for rec in self:
            rec.uniq_key = '%s|%s|%s' % (
                rec.model_id.id or 0, rec.button_type or '', rec.technical_name or '',
            )

    @api.depends('model_name', 'button_type', 'button_string', 'technical_name', 'is_global')
    def _compute_display_name(self):
        type_labels = dict(BUTTON_TYPE_SELECTION)
        for rec in self:
            label = rec.button_string or rec.technical_name or type_labels.get(
                rec.button_type, rec.button_type)
            scope = 'ALL MODELS' if rec.is_global else (rec.model_name or '?')
            rec.display_name = "[%s] %s" % (scope, label)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        empty = records.filtered(lambda r: not r.user_ids and not r.group_ids)
        if empty:
            raise ValidationError(_(
                "A button access rule must hide the button from at least one user or group."
            ))
        records._clear_rule_cache()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'user_ids' in vals or 'group_ids' in vals:
            empty = self.filtered(lambda r: r.exists() and not r.user_ids and not r.group_ids)
            if empty:
                empty.unlink()
        self._clear_rule_cache()
        return res

    def unlink(self):
        self._clear_rule_cache()
        return super().unlink()

    def _clear_rule_cache(self):
        for attr in (
            '_button_access_cache',
            '_button_access_rules_by_uid',
            '_button_access_exceptions_by_uid',
            '_button_access_inactive_profile_groups',
            '_access_profile_op_denied',
        ):
            cache = getattr(self.env.cr, attr, None)
            if cache is not None:
                cache.clear()

    def _inactive_profile_group_ids(self):
        """Generated profile groups that do not apply (archived or other company)."""
        cache = getattr(self.env.cr, '_button_access_inactive_profile_groups', None)
        if cache is None:
            cache = {}
            self.env.cr._button_access_inactive_profile_groups = cache
        cid = self.env.company.id
        if cid not in cache:
            ids = []
            if 'access.profile' in self.env:
                try:
                    profiles = self.env['access.profile'].sudo().with_context(
                        active_test=False
                    ).search([('generated_group_id', '!=', False)])
                    for profile in profiles:
                        if not profile.active:
                            ids.append(profile.generated_group_id.id)
                        elif (
                            profile.company_ids
                            and self.env.company not in profile.company_ids
                        ):
                            ids.append(profile.generated_group_id.id)
                except Exception:
                    ids = []
            cache[cid] = ids
        return cache[cid]

    def _cached_exceptions_for_uid(self, uid):
        cache = getattr(self.env.cr, '_button_access_exceptions_by_uid', None)
        if cache is None:
            cache = {}
            self.env.cr._button_access_exceptions_by_uid = cache
        if uid not in cache:
            if 'access.profile.exception' not in self.env:
                cache[uid] = []
            else:
                try:
                    recs = self.env['access.profile.exception'].sudo().search([
                        ('user_id', '=', uid),
                        ('profile_id.active', '=', True),
                    ])
                    cache[uid] = [{
                        'model': rec.model_id.model or None,
                        'type': rec.button_type,
                        'name': rec.technical_name or '',
                    } for rec in recs]
                except Exception:
                    cache[uid] = []
        return cache[uid]

    def _exception_allows(self, uid, model_name, button_type, technical_name):
        technical_name = technical_name or ''
        for exc in self._cached_exceptions_for_uid(uid):
            if exc['type'] != button_type:
                continue
            if exc['model'] and exc['model'] != model_name:
                continue
            if exc['name'] and exc['name'] != technical_name:
                continue
            return True
        return False

    def get_exceptions_for_current_user(self):
        uid = self.env.uid
        if uid == 1:
            return []
        return list(self._cached_exceptions_for_uid(uid))

    def _target_domain_for_uid(self, uid):
        user = self.env['res.users'].sudo().browse(uid)
        inactive = set(self._inactive_profile_group_ids())
        try:
            all_gids = user._get_group_ids()
        except Exception:
            all_gids = user.groups_id.ids
        group_ids = [gid for gid in all_gids if gid not in inactive]
        domain = ['|', ('user_ids', 'in', [uid])]
        if group_ids:
            domain += [('group_ids', 'in', group_ids)]
        else:
            domain += [(0, '=', 1)]
        return domain

    def _serialize_rule(self, rule):
        return {
            'model': rule.model_name or None,
            'type': rule.button_type,
            'name': rule.technical_name or '',
            'string': rule.button_string or '',
        }

    @api.model
    def get_rules_for_current_user(self):
        uid = self.env.uid
        if uid == 1:
            return []
        domain = [('active', '=', True)] + self._target_domain_for_uid(uid)
        rules = self.sudo().search(domain)
        serialized = [self._serialize_rule(r) for r in rules]
        seen = set()
        unique = []
        for item in serialized:
            if item['model'] and self._exception_allows(
                    uid, item['model'], item['type'], item['name']):
                continue
            key = (item['model'], item['type'], item['name'])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _cached_rules_for_uid(self):
        cache = getattr(self.env.cr, '_button_access_rules_by_uid', None)
        if cache is None:
            cache = {}
            self.env.cr._button_access_rules_by_uid = cache
        key = (self.env.uid, self.env.company.id)
        if key not in cache:
            cache[key] = self.get_rules_for_current_user()
        return cache[key]

    def rules_for_model(self, model_name):
        """Serialized rules that apply to model_name (specific + global, minus framework globals)."""
        uid = self.env.uid
        skip_global = is_framework_model(self.env, model_name)
        result = []
        for rule in self._cached_rules_for_uid():
            if self._exception_allows(uid, model_name, rule['type'], rule['name']):
                continue
            if rule['model'] == model_name:
                result.append(rule)
            elif not rule['model'] and not skip_global:
                result.append(rule)
        return result

    def _name_domain(self, button_type, technical_name):
        technical_name = technical_name or ''
        if button_type in ('report', 'action') and technical_name:
            return ['|', ('technical_name', '=', technical_name), ('technical_name', '=', '')]
        return [('technical_name', '=', technical_name)]

    def _is_blocked(self, model_name, button_type, technical_name=''):
        uid = self.env.uid
        if uid == 1:
            return False
        if self.env.context.get('button_access_skip'):
            return False
        technical_name = technical_name or ''
        if self._exception_allows(uid, model_name, button_type, technical_name):
            return False
        cache = getattr(self.env.cr, '_button_access_cache', None)
        if cache is None:
            cache = {}
            self.env.cr._button_access_cache = cache
        key = (uid, self.env.company.id, model_name, button_type, technical_name)
        if key in cache:
            return cache[key]

        skip_global = is_framework_model(self.env, model_name)
        domain = [
            ('button_type', '=', button_type),
            ('active', '=', True),
        ]
        domain += self._target_domain_for_uid(uid)
        domain += self._name_domain(button_type, technical_name)
        if skip_global:
            domain.append(('model_name', '=', model_name))
        else:
            domain = [
                '|', ('model_name', '=', model_name), ('model_id', '=', False),
            ] + domain

        blocked = bool(self.sudo().search_count(domain))
        cache[key] = blocked
        return blocked

    def enforce(self, model_name, button_type, technical_name=''):
        """Raise AccessError if the current user is not allowed to trigger this action."""
        if self.env.context.get('button_access_skip'):
            return
        try:
            blocked = self._is_blocked(model_name, button_type, technical_name or '')
        except AccessError:
            raise
        except Exception:
            _logger.exception(
                'button_access_manager: enforcement check failed, denying action.')
            raise AccessError(_(
                "This action has been restricted for your user account. "
                "Please contact your administrator if you believe this is a mistake."
            ))
        if blocked:
            _logger.info(
                'button_access_manager: blocked uid=%s model=%s type=%s name=%s',
                self.env.uid, model_name, button_type, technical_name)
            if 'access.block.log' in self.env:
                try:
                    self.env['access.block.log'].sudo().create({
                        'user_id': self.env.uid,
                        'model_name': model_name or '',
                        'button_type': button_type or '',
                        'technical_name': technical_name or '',
                    })
                except Exception:
                    _logger.exception(
                        'button_access_manager: could not write access.block.log')
            raise AccessError(_(
                "This action has been restricted for your user account. "
                "Please contact your administrator if you believe this is a mistake."
            ))

    def enforce_action_record(self, action):
        """Block a resolved ir.actions.* record for the current user."""
        if not action:
            return
        xmlid = ''
        try:
            xmlid = action.get_external_id().get(action.id) or ''
        except Exception:
            xmlid = ''
        model_name = (
            getattr(action, 'res_model', False)
            or getattr(action, 'model', False)
            or getattr(action, 'binding_model_id', False) and action.binding_model_id.model
            or False
        )
        names = [n for n in (str(action.id), xmlid, getattr(action, 'path', None) or '') if n]
        if action._name == 'ir.actions.report' or getattr(action, 'type', None) == 'ir.actions.report':
            btype = 'report'
            if not model_name:
                model_name = getattr(action, 'model', False)
        else:
            btype = 'action'
        if not model_name:
            # Still honour global report / action rules.
            model_name = ''
        for name in names or ['']:
            self.enforce(model_name, btype, name)
        if btype == 'report':
            self.enforce(model_name, 'report', '')

    @api.model
    def _create_or_update_rule(self, model_id, button_type, technical_name, button_string,
                               view_types, user_ids=None, group_ids=None):
        technical_name = technical_name or ''
        user_ids = list(user_ids or [])
        group_ids = list(group_ids or [])
        existing = self.search([
            ('model_id', '=', model_id),
            ('button_type', '=', button_type),
            ('technical_name', '=', technical_name),
        ], limit=1)
        if existing:
            vals = {
                'button_string': button_string or existing.button_string,
                'view_types': view_types or existing.view_types,
                'active': True,
            }
            commands = []
            if user_ids:
                commands = [(4, uid) for uid in user_ids]
                vals['user_ids'] = commands
            if group_ids:
                vals['group_ids'] = [(4, gid) for gid in group_ids]
            existing.write(vals)
            return existing
        return self.create({
            'model_id': model_id,
            'button_type': button_type,
            'technical_name': technical_name,
            'button_string': button_string,
            'view_types': view_types,
            'user_ids': [(6, 0, user_ids)] if user_ids else False,
            'group_ids': [(6, 0, group_ids)] if group_ids else False,
        })

    @api.model
    def _create_or_update_global_rule(self, button_type, technical_name, button_string,
                                      user_id=None, group_id=None):
        technical_name = technical_name or ''
        existing = self.search([
            ('model_id', '=', False),
            ('button_type', '=', button_type),
            ('technical_name', '=', technical_name),
        ], limit=1)
        if existing:
            vals = {'active': True}
            if user_id and user_id not in existing.user_ids.ids:
                vals['user_ids'] = [(4, user_id)]
            if group_id and group_id not in existing.group_ids.ids:
                vals['group_ids'] = [(4, group_id)]
            if len(vals) > 1 or not existing.active:
                existing.write(vals)
            return existing
        vals = {
            'model_id': False,
            'button_type': button_type,
            'technical_name': technical_name,
            'button_string': button_string,
            'view_types': 'all models',
        }
        if user_id:
            vals['user_ids'] = [(6, 0, [user_id])]
        if group_id:
            vals['group_ids'] = [(6, 0, [group_id])]
        return self.create(vals)

    @api.model
    def _remove_user_from_global_rule(self, button_type, technical_name, user_id):
        technical_name = technical_name or ''
        existing = self.search([
            ('model_id', '=', False),
            ('button_type', '=', button_type),
            ('technical_name', '=', technical_name),
            ('user_ids', 'in', [user_id]),
        ], limit=1)
        if existing:
            existing.write({'user_ids': [(3, user_id)]})

    @api.model
    def _remove_group_from_global_rule(self, button_type, technical_name, group_id):
        technical_name = technical_name or ''
        existing = self.search([
            ('model_id', '=', False),
            ('button_type', '=', button_type),
            ('technical_name', '=', technical_name),
            ('group_ids', 'in', [group_id]),
        ], limit=1)
        if existing:
            existing.write({'group_ids': [(3, group_id)]})

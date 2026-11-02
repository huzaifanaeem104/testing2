# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .constants import BUTTON_TYPE_SELECTION, GLOBAL_ACTIONS, is_framework_model

_logger = logging.getLogger(__name__)

VIEW_ONLY_FLAGS = (
    'restrict_new', 'restrict_delete', 'restrict_duplicate', 'restrict_import',
    'restrict_export', 'restrict_archive', 'restrict_print', 'restrict_confirm',
    'restrict_post',
)

PRESET_SELECTION = [
    ('view_only_all', 'View Only (all business models)'),
    ('sales_view_only', 'Sales View Only'),
    ('purchase_view_only', 'Purchase View Only'),
    ('accounting_no_post', 'Accounting — no Post / Confirm'),
    ('warehouse_operator', 'Warehouse Operator'),
]

OPERATION_PERM = {
    'read': 'perm_read',
    'write': 'perm_write',
    'create': 'perm_create',
    'unlink': 'perm_unlink',
}


class AccessProfile(models.Model):
    _name = 'access.profile'
    _description = 'Access Profile'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    description = fields.Text()
    user_ids = fields.Many2many(
        'res.users', 'access_profile_users_rel', 'profile_id', 'user_id',
        string='Users')
    group_ids = fields.Many2many(
        'res.groups', 'access_profile_groups_rel', 'profile_id', 'group_id',
        string='Also apply to Groups',
        help='Every member of these groups is assigned the generated profile group.')
    company_ids = fields.Many2many(
        'res.company', 'access_profile_company_rel', 'profile_id', 'company_id',
        string='Companies',
        help='Empty = all companies. When set, button blocks apply only in these '
             'companies. Native CRUD access rights are not written (they are not '
             'company-specific).')
    generated_group_id = fields.Many2one(
        'res.groups', string='Generated Group', readonly=True, copy=False,
        ondelete='restrict')
    model_line_ids = fields.One2many('access.profile.model', 'profile_id', string='Models')
    exception_ids = fields.One2many('access.profile.exception', 'profile_id', string='Exceptions')
    log_ids = fields.One2many(
        'access.profile.log', 'profile_id', string='Audit', copy=False)
    generated_access_ids = fields.One2many(
        'ir.model.access', compute='_compute_generated_access',
        string='Generated Access Rights', readonly=True)
    generated_rule_ids = fields.One2many(
        'ir.rule', compute='_compute_generated_rules',
        string='Generated Record Rules', readonly=True)
    button_access_rule_ids = fields.Many2many(
        'button.access.rule', compute='_compute_button_access_rule_ids',
        string='Hidden Buttons', readonly=True)
    hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'access_profile_hidden_menu_rel', 'profile_id', 'menu_id',
        string='Hidden Apps & Menus',
        context={'ir.ui.menu.full_list': True},
        help='Menus hidden for everyone on this profile via the generated group. '
             'Menu hiding is not company-specific: it applies in every company.')
    hidden_menu_rule_ids = fields.Many2many(
        'button.access.menu.rule', compute='_compute_hidden_menu_rule_ids',
        string='Hidden App / Menu Rules', readonly=True)

    restrict_new = fields.Boolean(string='New / Create')
    restrict_delete = fields.Boolean(string='Delete')
    restrict_duplicate = fields.Boolean(string='Duplicate')
    restrict_import = fields.Boolean(string='Import')
    restrict_export = fields.Boolean(string='Export')
    restrict_archive = fields.Boolean(string='Archive / Unarchive')
    restrict_print = fields.Boolean(string='Print (all reports)')
    restrict_cancel = fields.Boolean(string='Cancel')
    restrict_reset_draft = fields.Boolean(string='Reset to Draft / Set to Quotation')
    restrict_confirm = fields.Boolean(string='Confirm / Validate')
    restrict_post = fields.Boolean(string='Post (Confirm Invoices & Bills)')
    restrict_lock = fields.Boolean(string='Lock')
    restrict_unlock = fields.Boolean(string='Unlock')
    restrict_send_email = fields.Boolean(string='Send by Email')
    restrict_done = fields.Boolean(string='Mark Done / Close')

    @api.depends('model_line_ids', 'generated_group_id')
    def _compute_generated_access(self):
        Access = self.env['ir.model.access'].sudo()
        for rec in self:
            if not rec.id:
                rec.generated_access_ids = False
                continue
            rec.generated_access_ids = Access.search([
                ('name', '=like', 'access.profile.%s.%%' % rec.id),
            ])

    @api.depends('model_line_ids.record_rule_preset', 'model_line_ids.domain_force', 'generated_group_id')
    def _compute_generated_rules(self):
        Rule = self.env['ir.rule'].sudo()
        for rec in self:
            if not rec.id:
                rec.generated_rule_ids = False
                continue
            rec.generated_rule_ids = Rule.search([
                ('name', '=like', 'access.profile.%s.rule.%%' % rec.id),
            ])

    @api.depends('generated_group_id')
    def _compute_button_access_rule_ids(self):
        Rule = self.env['button.access.rule'].sudo()
        for rec in self:
            if rec.generated_group_id:
                rec.button_access_rule_ids = Rule.search([
                    ('group_ids', 'in', [rec.generated_group_id.id]),
                ])
            else:
                rec.button_access_rule_ids = False

    @api.depends('generated_group_id', 'hidden_menu_ids')
    def _compute_hidden_menu_rule_ids(self):
        Rule = self.env['button.access.menu.rule'].sudo()
        for rec in self:
            if rec.generated_group_id:
                rec.hidden_menu_rule_ids = Rule.search([
                    ('group_ids', 'in', [rec.generated_group_id.id]),
                ])
            else:
                rec.hidden_menu_rule_ids = False

    def _assigned_users(self):
        self.ensure_one()
        return (self.user_ids | self.group_ids.mapped('users')).filtered(lambda u: u.id != 1)

    def _access_name(self, model_name):
        self.ensure_one()
        return 'access.profile.%s.%s' % (self.id, model_name.replace('.', '_'))

    def _rule_name(self, model_name):
        self.ensure_one()
        return 'access.profile.%s.rule.%s' % (self.id, model_name.replace('.', '_'))

    def _ensure_generated_group(self):
        self.ensure_one()
        if self.generated_group_id:
            return self.generated_group_id
        category = self.env.ref(
            'button_access_manager.module_category_access_profiles', raise_if_not_found=False)
        if not category:
            category = self.env.ref('base.module_category_hidden', raise_if_not_found=False)
        group = self.env['res.groups'].sudo().create({
            'name': _('Access Profile: %s', self.name),
            'category_id': category.id if category else False,
            'comment': _('Generated by Button Access Manager. Manage from Access Profiles, not here.'),
        })
        self.with_context(access_profile_skip_sync=True).generated_group_id = group
        return group

    def _clear_generated_membership(self):
        """Drop generated-group membership and hide-menu links for archived profiles."""
        for rec in self.with_context(active_test=False):
            group = rec.generated_group_id
            if group:
                group.sudo().write({'users': [(5, 0, 0)]})
                rec._clear_menu_group_links()
            rec._log(_('Profile archived; generated group membership cleared.'))

    def _sync_generated(self):
        Rule = self.env['button.access.rule']
        records = self.with_context(active_test=False).browse(self.ids)
        for rec in records:
            if not rec.active:
                rec._clear_generated_membership()
                continue
            group = rec._ensure_generated_group()
            members = rec._assigned_users()
            group.sudo().write({
                'name': _('Access Profile: %s', rec.name),
                'users': [(6, 0, members.ids)],
            })
            rec._sync_button_flags(group)
            rec._sync_menu_flags(group)
            if rec.company_ids:
                rec._purge_generated_acl()
            else:
                rec._sync_model_acl(group)
            rec._log(_('Synchronized generated group, access rights, button rules, and hidden menus.'))
        Rule._clear_rule_cache()
        if 'button.access.menu.rule' in self.env:
            self.env['button.access.menu.rule']._clear_menu_hide_cache()

    def _sync_button_flags(self, group):
        self.ensure_one()
        Rule = self.env['button.access.rule'].sudo()
        for fname, _label, btype, aliases, strings in GLOBAL_ACTIONS:
            enabled = bool(self[fname])
            for alias, label in zip(aliases, strings):
                if enabled:
                    Rule._create_or_update_global_rule(
                        btype, alias, label, group_id=group.id)
                else:
                    Rule._remove_group_from_global_rule(btype, alias, group.id)

    def _sync_menu_flags(self, group):
        self.ensure_one()
        if 'button.access.menu.rule' not in self.env:
            return
        Rule = self.env['button.access.menu.rule'].sudo()
        want = set(self.hidden_menu_ids.ids)
        existing = Rule.search([('group_ids', 'in', [group.id])])
        existing_ids = set(existing.mapped('menu_id').ids)
        for menu_id in want - existing_ids:
            Rule._create_or_update_menu_rule(menu_id, group_ids=[group.id])
        for menu_id in existing_ids - want:
            Rule._remove_group_from_menu_rule(menu_id, group.id)

    def _clear_menu_group_links(self):
        self.ensure_one()
        group = self.generated_group_id
        if not group or 'button.access.menu.rule' not in self.env:
            return
        Rule = self.env['button.access.menu.rule'].sudo()
        rules = Rule.search([('group_ids', 'in', [group.id])])
        for rule in rules:
            rule.write({'group_ids': [(3, group.id)]})

    def _sync_model_acl(self, group):
        self.ensure_one()
        Access = self.env['ir.model.access'].sudo()
        IrRule = self.env['ir.rule'].sudo()
        keep_access = set()
        keep_rules = set()
        for line in self.model_line_ids:
            if not line.model_id or line.model_id.model not in self.env:
                continue
            access_name = self._access_name(line.model_id.model)
            keep_access.add(access_name)
            existing = Access.search([
                ('name', '=', access_name),
                ('group_id', '=', group.id),
                ('model_id', '=', line.model_id.id),
            ], limit=1)
            vals = {
                'name': access_name,
                'model_id': line.model_id.id,
                'group_id': group.id,
                'perm_read': line.perm_read,
                'perm_write': line.perm_write,
                'perm_create': line.perm_create,
                'perm_unlink': line.perm_unlink,
            }
            if existing:
                existing.write(vals)
            else:
                Access.create(vals)
            domain = line._record_rule_domain()
            rule_name = self._rule_name(line.model_id.model)
            existing_rule = IrRule.search([('name', '=', rule_name)], limit=1)
            if domain:
                keep_rules.add(rule_name)
                rule_vals = {
                    'name': rule_name,
                    'model_id': line.model_id.id,
                    'domain_force': domain,
                    'groups': [(6, 0, [group.id])],
                    'perm_read': True,
                    'perm_write': True,
                    'perm_create': True,
                    'perm_unlink': True,
                }
                if existing_rule:
                    existing_rule.write(rule_vals)
                else:
                    IrRule.create(rule_vals)
            elif existing_rule:
                existing_rule.unlink()
        leftover_access = Access.search([
            ('name', '=like', 'access.profile.%s.%%' % self.id),
            ('name', 'not in', list(keep_access) or ['__none__']),
        ])
        leftover_access.unlink()
        leftover_rules = IrRule.search([
            ('name', '=like', 'access.profile.%s.rule.%%' % self.id),
            ('name', 'not in', list(keep_rules) or ['__none__']),
        ])
        leftover_rules.unlink()

    def _purge_generated_acl(self):
        """Company-specific profiles do not write global ir.model.access."""
        self.ensure_one()
        self.env['ir.model.access'].sudo().search([
            ('name', '=like', 'access.profile.%s.%%' % self.id),
        ]).unlink()
        self.env['ir.rule'].sudo().search([
            ('name', '=like', 'access.profile.%s.rule.%%' % self.id),
        ]).unlink()

    def _log(self, message):
        self.ensure_one()
        if not self.id:
            return
        self.env['access.profile.log'].sudo().create({
            'profile_id': self.id,
            'user_id': self.env.uid,
            'message': message,
        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super(AccessProfile, self.with_context(access_profile_skip_sync=True)).create(vals_list)
        synced = self.browse(records.ids)
        synced._sync_generated()
        return synced

    def write(self, vals):
        ids = list(self.ids)
        res = super().write(vals)
        if not self.env.context.get('access_profile_skip_sync'):
            self.with_context(active_test=False).browse(ids)._sync_generated()
        return res

    def unlink(self):
        Access = self.env['ir.model.access'].sudo()
        IrRule = self.env['ir.rule'].sudo()
        Rule = self.env['button.access.rule'].sudo()
        groups = self.mapped('generated_group_id')
        for rec in self:
            Access.search([
                ('name', '=like', 'access.profile.%s.%%' % rec.id),
            ]).unlink()
            IrRule.search([
                ('name', '=like', 'access.profile.%s.rule.%%' % rec.id),
            ]).unlink()
            if rec.generated_group_id:
                rules = Rule.search([('group_ids', 'in', rec.generated_group_id.ids)])
                for rule in rules:
                    rule.write({'group_ids': [(3, rec.generated_group_id.id)]})
                if 'button.access.menu.rule' in self.env:
                    menu_rules = self.env['button.access.menu.rule'].sudo().search([
                        ('group_ids', 'in', rec.generated_group_id.ids),
                    ])
                    for rule in menu_rules:
                        rule.write({'group_ids': [(3, rec.generated_group_id.id)]})
        self.with_context(access_profile_skip_sync=True).write({'generated_group_id': False})
        res = super().unlink()
        groups.sudo().unlink()
        Rule._clear_rule_cache()
        if 'button.access.menu.rule' in self.env:
            self.env['button.access.menu.rule']._clear_menu_hide_cache()
        return res

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault('name', _('%s (copy)', self.name))
        default['generated_group_id'] = False
        return super().copy(default)

    def action_sync(self):
        self._sync_generated()
        return True

    def action_open_scan(self):
        self.ensure_one()
        group = self._ensure_generated_group()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Scan & Hide Buttons'),
            'res_model': 'button.access.scan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_group_ids': [(6, 0, [group.id])],
                'lock_group_field': True,
            },
        }

    def action_open_menu_wizard(self):
        self.ensure_one()
        group = self._ensure_generated_group()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Hide Apps & Menus'),
            'res_model': 'button.access.menu.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_profile_id': self.id,
                'default_group_ids': [(6, 0, [group.id])],
                'lock_group_field': True,
            },
        }

    def action_open_preset(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apply Preset'),
            'res_model': 'access.profile.preset.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_profile_id': self.id},
        }

    def apply_preset(self, preset):
        self.ensure_one()
        if preset == 'view_only_all':
            self._preset_view_only_models(self._business_model_names())
            self._preset_set_flags(VIEW_ONLY_FLAGS)
        elif preset == 'sales_view_only':
            self._preset_view_only_models(['sale.order', 'sale.order.line'])
            self._preset_set_flags(VIEW_ONLY_FLAGS)
        elif preset == 'purchase_view_only':
            self._preset_view_only_models([
                'purchase.order', 'purchase.order.line', 'purchase.requisition',
            ])
            self._preset_set_flags(VIEW_ONLY_FLAGS)
        elif preset == 'accounting_no_post':
            self._add_model_line('account.move', perm_write=True, perm_create=True)
            self._add_model_line('account.move.line', perm_write=True, perm_create=True)
            self._preset_set_flags(('restrict_post', 'restrict_confirm'))
        elif preset == 'warehouse_operator':
            self._add_model_line('stock.picking', perm_write=True, perm_create=True)
            self._add_model_line('stock.move', perm_write=True, perm_create=True)
            group = self._ensure_generated_group()
            picking = self.env['ir.model'].sudo()._get('stock.picking')
            if picking:
                Rule = self.env['button.access.rule'].sudo()
                for method, label in (
                    ('button_validate', 'Validate'),
                    ('action_confirm', 'Confirm'),
                ):
                    Rule._create_or_update_rule(
                        model_id=picking.id,
                        button_type='object',
                        technical_name=method,
                        button_string=label,
                        view_types='form',
                        group_ids=[group.id],
                    )
        else:
            raise UserError(_('Unknown preset: %s', preset))
        self._sync_generated()
        return True

    def _preset_set_flags(self, flags):
        vals = {fname: True for fname in flags}
        self.with_context(access_profile_skip_sync=True).write(vals)

    def _preset_view_only_models(self, model_names):
        for name in model_names:
            self._add_model_line(
                name, perm_read=True, perm_write=False,
                perm_create=False, perm_unlink=False)

    def _add_model_line(self, model_name, perm_read=True, perm_write=True,
                        perm_create=True, perm_unlink=True):
        self.ensure_one()
        if model_name not in self.env:
            return self.env['access.profile.model']
        model = self.env['ir.model'].sudo()._get(model_name)
        if not model:
            return self.env['access.profile.model']
        existing = self.model_line_ids.filtered(lambda l: l.model_id.id == model.id)
        vals = {
            'perm_read': perm_read,
            'perm_write': perm_write,
            'perm_create': perm_create,
            'perm_unlink': perm_unlink,
        }
        if existing:
            existing.with_context(access_profile_skip_sync=True).write(vals)
            return existing[:1]
        return self.env['access.profile.model'].with_context(access_profile_skip_sync=True).create({
            'profile_id': self.id,
            'model_id': model.id,
            **vals,
        })

    def _business_model_names(self):
        skip = {
            'res.users', 'res.groups', 'res.company', 'res.currency',
            'res.country', 'res.lang',
        }
        actions = self.env['ir.actions.act_window'].sudo().search([('res_model', '!=', False)])
        names = set()
        for name in actions.mapped('res_model'):
            if (
                not name or name not in self.env or name in skip
                or is_framework_model(self.env, name)
            ):
                continue
            names.add(name)
        return sorted(names)

    @api.model
    def _operation_denied(self, model_name, operation):
        """True when an active, all-company profile denies this CRUD operation."""
        uid = self.env.uid
        if uid == 1 or self.env.su:
            return False
        if not model_name or is_framework_model(self.env, model_name):
            return False
        perm_field = OPERATION_PERM.get(operation)
        if not perm_field:
            return False
        btype = {'create': 'create', 'unlink': 'delete'}.get(operation)
        if btype and self.env['button.access.rule']._exception_allows(
                uid, model_name, btype, ''):
            return False
        cache = getattr(self.env.cr, '_access_profile_op_denied', None)
        if cache is None:
            cache = {}
            self.env.cr._access_profile_op_denied = cache
        key = (uid, self.env.company.id, model_name, operation)
        if key in cache:
            return cache[key]
        user_groups = set(self.env.user.groups_id.ids)
        lines = self.env['access.profile.model'].sudo().search([
            ('model_id.model', '=', model_name),
            (perm_field, '=', False),
            ('profile_id.active', '=', True),
            ('profile_id.generated_group_id', '!=', False),
            ('profile_id.company_ids', '=', False),
        ])
        denied = False
        for line in lines:
            group_id = line.profile_id.generated_group_id.id
            if group_id in user_groups:
                denied = True
                break
        cache[key] = denied
        return denied


class AccessProfileModel(models.Model):
    _name = 'access.profile.model'
    _description = 'Access Profile Model Line'
    _order = 'model_id'

    profile_id = fields.Many2one('access.profile', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', string='Model')
    perm_read = fields.Boolean(string='Read', default=True)
    perm_write = fields.Boolean(string='Write', default=True)
    perm_create = fields.Boolean(string='Create', default=True)
    perm_unlink = fields.Boolean(string='Delete', default=True)
    record_rule_preset = fields.Selection([
        ('false', 'No extra record rule'),
        ('own_documents', 'Own documents only'),
        ('own_company', 'Own company only'),
        ('own_department', 'Own department only'),
        ('custom', 'Custom domain'),
    ], default='false', required=True, string='Record Rule')
    domain_force = fields.Char(
        string='Custom Domain',
        help="Python domain, e.g. [('user_id', '=', user.id)]")

    _sql_constraints = [
        ('uniq_profile_model', 'unique(profile_id, model_id)',
         'This model is already on the profile.'),
    ]

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('access_profile_skip_sync'):
            self.mapped('profile_id')._sync_generated()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('access_profile_skip_sync'):
            records.mapped('profile_id')._sync_generated()
        return records

    def unlink(self):
        profiles = self.mapped('profile_id')
        res = super().unlink()
        if not self.env.context.get('access_profile_skip_sync'):
            profiles._sync_generated()
        return res

    def _record_rule_domain(self):
        self.ensure_one()
        preset = self.record_rule_preset
        if not preset or preset == 'false':
            return False
        model_name = self.model_id.model
        if model_name not in self.env:
            return False
        Model = self.env[model_name]
        if preset == 'own_documents':
            for fname in ('user_id', 'create_uid'):
                field = Model._fields.get(fname)
                if field and getattr(field, 'store', False) and field.type == 'many2one':
                    return "[('%s', '=', user.id)]" % fname
            return False
        if preset == 'own_company':
            if 'company_id' in Model._fields:
                return "[('company_id', 'in', company_ids)]"
            if 'company_ids' in Model._fields:
                return "[('company_ids', 'in', company_ids)]"
            return False
        if preset == 'own_department':
            if 'department_id' in Model._fields:
                return "[('department_id', '=', user.employee_id.department_id.id)]"
            return False
        if preset == 'custom':
            return self.domain_force or False
        return False


class AccessProfileException(models.Model):
    _name = 'access.profile.exception'
    _description = 'Access Profile Exception'
    _order = 'user_id, button_type'

    profile_id = fields.Many2one('access.profile', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    model_id = fields.Many2one(
        'ir.model', ondelete='cascade',
        help='Empty = this button type on every model.')
    button_type = fields.Selection(
        BUTTON_TYPE_SELECTION, required=True, default='create')
    technical_name = fields.Char(
        default='',
        help='Empty = every technical name of this button type.')

    def matches(self, model_name, button_type, technical_name):
        self.ensure_one()
        if self.button_type != button_type:
            return False
        if self.model_id and self.model_id.model != model_name:
            return False
        if self.technical_name and (self.technical_name or '') != (technical_name or ''):
            return False
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['button.access.rule']._clear_rule_cache()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env['button.access.rule']._clear_rule_cache()
        return res

    def unlink(self):
        self.env['button.access.rule']._clear_rule_cache()
        return super().unlink()


class AccessProfileLog(models.Model):
    _name = 'access.profile.log'
    _description = 'Access Profile Audit Log'
    _order = 'id desc'

    profile_id = fields.Many2one('access.profile', ondelete='cascade')
    user_id = fields.Many2one('res.users', default=lambda self: self.env.uid, readonly=True)
    message = fields.Char(required=True, readonly=True)
    model_name = fields.Char(readonly=True)
    button_type = fields.Char(readonly=True)
    technical_name = fields.Char(readonly=True)


class AccessBlockLog(models.Model):
    _name = 'access.block.log'
    _description = 'Blocked Button Action Log'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', readonly=True)
    model_name = fields.Char(readonly=True, index=True)
    button_type = fields.Char(readonly=True)
    technical_name = fields.Char(readonly=True)

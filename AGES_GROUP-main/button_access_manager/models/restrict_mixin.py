# -*- coding: utf-8 -*-
from odoo import fields, models

from .constants import GLOBAL_ACTIONS


class ButtonAccessRestrictMixin(models.AbstractModel):
    """Quick Global Restriction checkboxes shared by users and groups.

    Checkboxes reflect *direct* membership on the rule (this user, or this
    group). Inherited group rules still hide/block for the user, but do not
    tick the user-form boxes — otherwise saving the user would copy group
    rules onto the user.
    """
    _name = 'button.access.restrict.mixin'
    _description = 'Button Access Restriction Checkboxes'

    restrict_new = fields.Boolean(
        string='New / Create', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_new')
    restrict_delete = fields.Boolean(
        string='Delete', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_delete')
    restrict_duplicate = fields.Boolean(
        string='Duplicate', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_duplicate')
    restrict_import = fields.Boolean(
        string='Import', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_import')
    restrict_export = fields.Boolean(
        string='Export', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_export')
    restrict_archive = fields.Boolean(
        string='Archive / Unarchive', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_archive')
    restrict_print = fields.Boolean(
        string='Print (all reports)', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_print')
    restrict_cancel = fields.Boolean(
        string='Cancel', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_cancel')
    restrict_reset_draft = fields.Boolean(
        string='Reset to Draft / Set to Quotation', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_reset_draft')
    restrict_confirm = fields.Boolean(
        string='Confirm / Validate', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_confirm')
    restrict_post = fields.Boolean(
        string='Post (Confirm Invoices & Bills)', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_post')
    restrict_lock = fields.Boolean(
        string='Lock', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_lock')
    restrict_unlock = fields.Boolean(
        string='Unlock', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_unlock')
    restrict_send_email = fields.Boolean(
        string='Send by Email', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_send_email')
    restrict_done = fields.Boolean(
        string='Mark Done / Close', compute='_compute_global_restrictions',
        inverse='_inverse_restrict_done')

    def _button_access_target_domain(self):
        raise NotImplementedError

    def _button_access_add_global(self, button_type, alias, label):
        raise NotImplementedError

    def _button_access_remove_global(self, button_type, alias):
        raise NotImplementedError

    def _compute_global_restrictions(self):
        Rule = self.env['button.access.rule'].sudo()
        by_key = {fname: (btype, aliases) for fname, _label, btype, aliases, _strings in GLOBAL_ACTIONS}
        for record in self:
            if not record.id:
                for fname in by_key:
                    record[fname] = False
                continue
            target = record._button_access_target_domain()
            for fname, (btype, aliases) in by_key.items():
                found = False
                for alias in aliases:
                    domain = [
                        ('model_id', '=', False),
                        ('button_type', '=', btype),
                        ('technical_name', '=', alias or ''),
                        ('active', '=', True),
                    ] + target
                    if Rule.search_count(domain):
                        found = True
                        break
                record[fname] = found

    def _toggle_global_action(self, button_type, aliases, strings, enable):
        self.ensure_one()
        for alias, label in zip(aliases, strings):
            if enable:
                self._button_access_add_global(button_type, alias, label)
            else:
                self._button_access_remove_global(button_type, alias)

    def _apply_global_toggle(self, field_name):
        entry = next(e for e in GLOBAL_ACTIONS if e[0] == field_name)
        _fname, _label, btype, aliases, strings = entry
        for record in self:
            record._toggle_global_action(btype, aliases, strings, record[field_name])

    def _inverse_restrict_new(self):
        self._apply_global_toggle('restrict_new')

    def _inverse_restrict_delete(self):
        self._apply_global_toggle('restrict_delete')

    def _inverse_restrict_duplicate(self):
        self._apply_global_toggle('restrict_duplicate')

    def _inverse_restrict_import(self):
        self._apply_global_toggle('restrict_import')

    def _inverse_restrict_export(self):
        self._apply_global_toggle('restrict_export')

    def _inverse_restrict_archive(self):
        self._apply_global_toggle('restrict_archive')

    def _inverse_restrict_print(self):
        self._apply_global_toggle('restrict_print')

    def _inverse_restrict_cancel(self):
        self._apply_global_toggle('restrict_cancel')

    def _inverse_restrict_reset_draft(self):
        self._apply_global_toggle('restrict_reset_draft')

    def _inverse_restrict_confirm(self):
        self._apply_global_toggle('restrict_confirm')

    def _inverse_restrict_post(self):
        self._apply_global_toggle('restrict_post')

    def _inverse_restrict_lock(self):
        self._apply_global_toggle('restrict_lock')

    def _inverse_restrict_unlock(self):
        self._apply_global_toggle('restrict_unlock')

    def _inverse_restrict_send_email(self):
        self._apply_global_toggle('restrict_send_email')

    def _inverse_restrict_done(self):
        self._apply_global_toggle('restrict_done')

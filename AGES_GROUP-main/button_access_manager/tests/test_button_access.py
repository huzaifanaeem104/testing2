# -*- coding: utf-8 -*-
from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestButtonAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env['button.access.rule']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.user = new_test_user(
            cls.env, login='bam_restricted', password='password',
            groups='base.group_user,base.group_partner_manager')
        cls.user2 = new_test_user(
            cls.env, login='bam_restricted2', password='password',
            groups='base.group_user,base.group_partner_manager')

    def _global_create_rule(self, users=None, groups=None):
        vals = {
            'model_id': False,
            'button_type': 'create',
            'technical_name': '',
            'button_string': 'New',
        }
        if users:
            vals['user_ids'] = [(6, 0, users.ids if hasattr(users, 'ids') else list(users))]
        if groups:
            vals['group_ids'] = [(6, 0, groups.ids if hasattr(groups, 'ids') else list(groups))]
        return self.Rule.create(vals)

    def test_internal_user_receives_serialized_rules(self):
        self._global_create_rule(users=self.user)
        rules = self.Rule.with_user(self.user).get_rules_for_current_user()
        self.assertTrue(rules)
        self.assertTrue(any(r['type'] == 'create' and not r['model'] for r in rules))
        empty = self.Rule.with_user(self.user2).get_rules_for_current_user()
        self.assertFalse(empty)

    def test_web_save_and_create_blocked(self):
        self._global_create_rule(users=self.user)
        Partner = self.env['res.partner'].with_user(self.user)
        with self.assertRaises(AccessError) as error:
            Partner.create({'name': 'Blocked Partner'})
        self.assertIn('restricted for your user account', str(error.exception))
        with self.assertRaises(AccessError) as error:
            Partner.web_save({'name': 'Blocked Save'}, {})
        self.assertIn('restricted for your user account', str(error.exception))

    def test_superuser_never_blocked(self):
        self._global_create_rule(users=self.user)
        root = self.env.ref('base.user_root')
        partner = self.env['res.partner'].with_user(root).create({'name': 'Superuser Partner'})
        self.assertTrue(partner.exists())

    def test_global_new_does_not_block_mail_message(self):
        if 'mail.message' not in self.env:
            self.skipTest('mail is not installed')
        self._global_create_rule(users=self.user)
        partner = self.env['res.partner'].create({'name': 'Chatter Partner'})
        message = self.env['mail.message'].with_user(self.user).create({
            'body': 'still allowed',
            'message_type': 'comment',
            'model': 'res.partner',
            'res_id': partner.id,
        })
        self.assertTrue(message.exists())

    def test_export_blocked(self):
        self.Rule.create({
            'model_id': False,
            'button_type': 'export',
            'technical_name': '',
            'button_string': 'Export',
            'user_ids': [(6, 0, [self.user.id])],
        })
        partner = self.env['res.partner'].create({'name': 'Export Partner'})
        with self.assertRaises(AccessError):
            partner.with_user(self.user).export_data(['name'])

    def test_archive_object_blocked(self):
        self.Rule.create({
            'model_id': False,
            'button_type': 'object',
            'technical_name': 'action_archive',
            'button_string': 'Archive',
            'user_ids': [(6, 0, [self.user.id])],
        })
        partner = self.env['res.partner'].create({'name': 'Archive Partner'})
        with self.assertRaises(AccessError):
            partner.with_user(self.user).action_archive()

    def test_report_action_blocked(self):
        self.Rule.create({
            'model_id': False,
            'button_type': 'report',
            'technical_name': '',
            'button_string': 'Print',
            'user_ids': [(6, 0, [self.user.id])],
        })
        report = self.env['ir.actions.report'].search([('model', '=', 'res.partner')], limit=1)
        self.assertTrue(
            self.Rule.with_user(self.user)._is_blocked('res.partner', 'report', ''),
        )
        if report:
            with self.assertRaises(AccessError):
                self.Rule.with_user(self.user).enforce_action_record(report)

    def test_removing_user_does_not_unhide_other_user(self):
        rule = self._global_create_rule(users=self.user | self.user2)
        rule.write({'user_ids': [(3, self.user.id)]})
        self.assertTrue(rule.exists())
        self.assertIn(self.user2, rule.user_ids)
        self.assertNotIn(self.user, rule.user_ids)
        self.env['res.partner'].with_user(self.user).create({'name': 'User A can create'})
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.user2).create({'name': 'User B blocked'})

    def test_group_rule_applies_without_user_ids(self):
        group = self.env['res.groups'].create({'name': 'BAM Hide Create'})
        self.user.groups_id = [(4, group.id)]
        self._global_create_rule(groups=group)
        self.assertTrue(
            self.Rule.with_user(self.user)._is_blocked('res.partner', 'create'))
        self.assertFalse(
            self.Rule.with_user(self.user2)._is_blocked('res.partner', 'create'))
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.user).create({'name': 'Group blocked'})
        self.env['res.partner'].with_user(self.user2).create({'name': 'Other user allowed'})

    def test_get_view_strips_create_and_named_buttons(self):
        self._global_create_rule(users=self.user)
        list_arch = self.env['res.partner'].with_user(self.user).get_view(view_type='list')['arch']
        self.assertTrue(
            'create="false"' in list_arch or "create='false'" in list_arch,
            list_arch[:500],
        )

        form_arch = self.env['res.partner'].get_view(view_type='form')['arch']
        root = etree.fromstring(form_arch.encode('utf-8'))
        named = root.xpath('//button[@name]')
        if not named:
            self.skipTest('res.partner form has no named buttons to strip')
        button_name = named[0].get('name')
        btn_type = named[0].get('type') or 'object'
        rule_type = 'action' if btn_type == 'action' else 'object'
        self.Rule.create({
            'model_id': self.partner_model.id,
            'button_type': rule_type,
            'technical_name': button_name,
            'button_string': named[0].get('string') or button_name,
            'user_ids': [(6, 0, [self.user.id])],
        })
        stripped = self.env['res.partner'].with_user(self.user).get_view(view_type='form')['arch']
        stripped_root = etree.fromstring(stripped.encode('utf-8'))
        still = stripped_root.xpath('//button[@name=$name]', name=button_name)
        self.assertFalse(still)

    def test_copy_wizard_adds_target_user(self):
        self._global_create_rule(users=self.user)
        wizard = self.env['button.access.copy.wizard'].create({
            'source_user_id': self.user.id,
            'target_user_ids': [(6, 0, [self.user2.id])],
        })
        wizard.action_copy()
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.user2).create({'name': 'Copied block'})


@tagged('post_install', '-at_install')
class TestButtonAccessHttp(HttpCase):

    def test_session_info_and_json_route_for_internal_user(self):
        user = new_test_user(
            self.env, login='bam_http', password='password',
            groups='base.group_user,base.group_partner_manager')
        self.env['button.access.rule'].create({
            'model_id': False,
            'button_type': 'create',
            'technical_name': '',
            'button_string': 'New',
            'user_ids': [(6, 0, [user.id])],
        })
        self.authenticate('bam_http', 'password')
        info = self.make_jsonrpc_request('/web/session/get_session_info', {})
        rules = info.get('button_access_rules') or []
        self.assertTrue(any(r.get('type') == 'create' for r in rules), rules)
        routed = self.make_jsonrpc_request('/button_access_manager/rules', {})
        self.assertTrue(any(r.get('type') == 'create' for r in routed), routed)

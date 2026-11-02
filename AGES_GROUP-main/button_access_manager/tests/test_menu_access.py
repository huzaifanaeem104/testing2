# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestMenuAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env['button.access.menu.rule']
        cls.Menu = cls.env['ir.ui.menu']
        cls.user = new_test_user(
            cls.env, login='bam_menu_a', password='password',
            groups='base.group_user,base.group_partner_manager')
        cls.user2 = new_test_user(
            cls.env, login='bam_menu_b', password='password',
            groups='base.group_user,base.group_partner_manager')
        cls.action = cls.env['ir.actions.act_window'].create({
            'name': 'BAM Menu Test Action',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
        })
        cls.action_other = cls.env['ir.actions.act_window'].create({
            'name': 'BAM Menu Other Action',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
        })
        cls.root = cls.Menu.create({'name': 'BAM Test App'})
        cls.child = cls.Menu.create({
            'name': 'BAM Test Child',
            'parent_id': cls.root.id,
            'action': 'ir.actions.act_window,%s' % cls.action.id,
        })
        cls.folder = cls.Menu.create({
            'name': 'BAM Test Folder',
            'parent_id': cls.root.id,
        })
        cls.leaf = cls.Menu.create({
            'name': 'BAM Test Leaf',
            'parent_id': cls.folder.id,
            'action': 'ir.actions.act_window,%s' % cls.action_other.id,
        })
        cls.shared_root = cls.Menu.create({'name': 'BAM Shared App'})
        cls.shared_child = cls.Menu.create({
            'name': 'BAM Shared Child',
            'parent_id': cls.shared_root.id,
            'action': 'ir.actions.act_window,%s' % cls.action.id,
        })

    def _load(self, user):
        return self.Menu.with_user(user).load_menus(False)

    def _menu_ids(self, payload):
        return {key for key in payload if key != 'root'}

    def test_catalog_includes_created_root_and_drops_when_unlinked(self):
        apps = self.Rule.get_installed_home_apps()
        ids = {row['menu_id'] for row in apps}
        self.assertIn(self.root.id, ids)
        ghost = self.Menu.create({'name': 'BAM Ghost App'})
        apps = self.Rule.get_installed_home_apps()
        self.assertIn(ghost.id, {row['menu_id'] for row in apps})
        ghost.unlink()
        apps = self.Rule.get_installed_home_apps()
        self.assertNotIn(ghost.id, {row['menu_id'] for row in apps})

    def test_unique_merge_and_empty_rule_unlinks(self):
        first = self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        second = self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user2.id])
        self.assertEqual(first, second)
        self.assertEqual(set(first.user_ids.ids), {self.user.id, self.user2.id})
        first.write({'user_ids': [(5, 0, 0)]})
        self.assertFalse(first.exists())

    def test_hide_root_from_user_a_only(self):
        self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        payload_a = self._load(self.user)
        payload_b = self._load(self.user2)
        self.assertNotIn(self.root.id, self._menu_ids(payload_a))
        self.assertNotIn(self.child.id, self._menu_ids(payload_a))
        self.assertIn(self.root.id, payload_b['root']['children'])
        self.assertIn(self.root.id, self._menu_ids(payload_b))

    def test_hide_child_only_keeps_root_when_sibling_remains(self):
        self.Rule._create_or_update_menu_rule(self.child.id, user_ids=[self.user.id])
        payload = self._load(self.user)
        self.assertIn(self.root.id, payload['root']['children'])
        self.assertNotIn(self.child.id, self._menu_ids(payload))
        self.assertIn(self.leaf.id, self._menu_ids(payload))

    def test_hide_parent_folder_omits_descendants(self):
        self.Rule._create_or_update_menu_rule(self.folder.id, user_ids=[self.user.id])
        payload = self._load(self.user)
        self.assertNotIn(self.folder.id, self._menu_ids(payload))
        self.assertNotIn(self.leaf.id, self._menu_ids(payload))
        self.assertIn(self.root.id, payload['root']['children'])
        self.assertIn(self.child.id, self._menu_ids(payload))

    def test_empty_folder_hides_root_when_all_action_children_hidden(self):
        self.Rule._create_or_update_menu_rule(self.child.id, user_ids=[self.user.id])
        self.Rule._create_or_update_menu_rule(self.leaf.id, user_ids=[self.user.id])
        payload = self._load(self.user)
        self.assertNotIn(self.root.id, payload['root']['children'])
        self.assertNotIn(self.root.id, self._menu_ids(payload))
        payload_b = self._load(self.user2)
        self.assertIn(self.root.id, payload_b['root']['children'])

    def test_same_groups_cache_does_not_leak(self):
        self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        payload_a = self._load(self.user)
        payload_b = self._load(self.user2)
        self.assertNotIn(self.root.id, self._menu_ids(payload_a))
        self.assertIn(self.root.id, self._menu_ids(payload_b))

    def test_superuser_sees_everything(self):
        self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        root = self.env.ref('base.user_root')
        payload = self.Menu.with_user(root).load_menus(False)
        self.assertIn(self.root.id, self._menu_ids(payload))
        self.assertFalse(self.Rule.hidden_menu_ids_for_uid(1))

    def test_full_list_search_still_returns_hidden_menus(self):
        self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        hidden = self.Menu.with_user(self.user).search([('id', '=', self.root.id)])
        self.assertFalse(hidden)
        full = self.Menu.with_user(self.user).with_context(
            {'ir.ui.menu.full_list': True}).search([('id', '=', self.root.id)])
        self.assertEqual(full, self.root)

    def test_action_block_and_shared_and_unbound(self):
        self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        # Shared: same action still on shared_child which is visible.
        self.Rule.with_user(self.user).enforce_action(self.action)
        self.Rule._create_or_update_menu_rule(self.shared_root.id, user_ids=[self.user.id])
        with self.assertRaises(AccessError) as error:
            self.Rule.with_user(self.user).enforce_action(self.action)
        self.assertIn('restricted for your user account', str(error.exception))
        self.Rule.with_user(self.user2).enforce_action(self.action)
        unbound = self.env['ir.actions.act_window'].create({
            'name': 'BAM Unbound Wizard',
            'res_model': 'res.partner',
            'view_mode': 'form',
            'target': 'new',
        })
        self.Rule.with_user(self.user).enforce_action(unbound)

    def test_profile_hides_and_archive_restores(self):
        profile = self.env['access.profile'].create({
            'name': 'Hide BAM App',
            'user_ids': [(6, 0, [self.user.id])],
            'hidden_menu_ids': [(6, 0, [self.root.id])],
        })
        payload = self._load(self.user)
        self.assertNotIn(self.root.id, self._menu_ids(payload))
        payload_b = self._load(self.user2)
        self.assertIn(self.root.id, self._menu_ids(payload_b))
        profile.write({'active': False})
        payload = self._load(self.user)
        self.assertIn(self.root.id, payload['root']['children'])

    def test_cannot_hide_protected_menu_from_admin(self):
        settings = self.env.ref('base.menu_administration', raise_if_not_found=False)
        if not settings:
            self.skipTest('base.menu_administration is missing')
        admin = self.env.ref('base.user_admin')
        with self.assertRaises(UserError):
            self.Rule.create({
                'menu_id': settings.id,
                'user_ids': [(6, 0, [admin.id])],
            })
        self.Rule._create_or_update_menu_rule(settings.id, user_ids=[self.user.id])

    def test_deleting_menu_deletes_rule(self):
        extra = self.Menu.create({'name': 'BAM Disposable App'})
        rule = self.Rule._create_or_update_menu_rule(extra.id, user_ids=[self.user.id])
        extra.unlink()
        self.assertFalse(rule.exists())

    def test_empty_rule_requires_user_or_group(self):
        with self.assertRaises(ValidationError):
            self.Rule.create({'menu_id': self.root.id})

    def test_copy_menus_onto_existing_rule(self):
        self.Rule._create_or_update_menu_rule(self.root.id, user_ids=[self.user.id])
        wizard = self.env['button.access.copy.wizard'].create({
            'source_user_id': self.user.id,
            'target_user_ids': [(6, 0, [self.user2.id])],
            'copy_buttons': False,
            'copy_menus': True,
        })
        wizard.action_copy()
        payload = self._load(self.user2)
        self.assertNotIn(self.root.id, self._menu_ids(payload))
        rules = self.Rule.search([('menu_id', '=', self.root.id)])
        self.assertEqual(len(rules), 1)
        self.assertEqual(set(rules.user_ids.ids), {self.user.id, self.user2.id})

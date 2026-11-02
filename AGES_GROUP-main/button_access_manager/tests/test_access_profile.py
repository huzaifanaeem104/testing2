# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestAccessProfile(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env['access.profile']
        cls.Rule = cls.env['button.access.rule']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.user = new_test_user(
            cls.env, login='bam_profile_user', password='password',
            groups='base.group_user,base.group_partner_manager')
        cls.user2 = new_test_user(
            cls.env, login='bam_profile_user2', password='password',
            groups='base.group_user,base.group_partner_manager')

    def _view_only_profile(self, users=None, extra=None):
        vals = {
            'name': 'View Only',
            'restrict_new': True,
            'restrict_delete': True,
            'restrict_duplicate': True,
            'restrict_import': True,
            'restrict_export': True,
            'restrict_archive': True,
            'restrict_print': True,
            'restrict_confirm': True,
            'restrict_post': True,
            'model_line_ids': [(0, 0, {
                'model_id': self.partner_model.id,
                'perm_read': True,
                'perm_write': False,
                'perm_create': False,
                'perm_unlink': False,
            })],
        }
        if users:
            vals['user_ids'] = [(6, 0, users.ids)]
        if extra:
            vals.update(extra)
        return self.Profile.create(vals)

    def test_view_only_blocks_partner_create_and_get_view(self):
        self._view_only_profile(users=self.user)
        Partner = self.env['res.partner'].with_user(self.user)
        with self.assertRaises(AccessError):
            Partner.create({'name': 'Blocked by profile'})
        list_arch = Partner.get_view(view_type='list')['arch']
        self.assertTrue(
            'create="false"' in list_arch or "create='false'" in list_arch,
            list_arch[:500],
        )
        self.env['res.partner'].with_user(self.user2).create({'name': 'Other user allowed'})

    def test_exception_allows_partner_create_only(self):
        profile = self._view_only_profile(users=self.user)
        profile.write({
            'exception_ids': [(0, 0, {
                'user_id': self.user.id,
                'model_id': self.partner_model.id,
                'button_type': 'create',
                'technical_name': '',
            })],
        })
        partner = self.env['res.partner'].with_user(self.user).create({
            'name': 'Exception create',
        })
        self.assertTrue(partner.exists())
        self.assertFalse(
            self.Rule.with_user(self.user)._is_blocked('res.partner', 'create'))
        self.assertTrue(
            self.Rule.with_user(self.user)._is_blocked('res.bank', 'create'))

    def test_sales_preset_skips_missing_model(self):
        profile = self.Profile.create({'name': 'Sales VO'})
        profile.apply_preset('sales_view_only')
        sale_lines = profile.model_line_ids.filtered(
            lambda line: line.model_id.model == 'sale.order')
        if 'sale.order' in self.env:
            self.assertTrue(sale_lines)
        else:
            self.assertFalse(sale_lines)
        self.assertFalse(profile.model_line_ids.filtered(
            lambda line: line.model_id.model == 'not.installed.model'))

    def test_superuser_never_blocked_by_profile(self):
        self._view_only_profile(users=self.user)
        root = self.env.ref('base.user_root')
        partner = self.env['res.partner'].with_user(root).create({'name': 'Root still creates'})
        self.assertTrue(partner.exists())

    def test_mail_message_create_under_global_new(self):
        if 'mail.message' not in self.env:
            self.skipTest('mail is not installed')
        self._view_only_profile(users=self.user)
        partner = self.env['res.partner'].create({'name': 'Chatter Partner'})
        message = self.env['mail.message'].with_user(self.user).create({
            'body': 'still allowed',
            'message_type': 'comment',
            'model': 'res.partner',
            'res_id': partner.id,
        })
        self.assertTrue(message.exists())

    def test_unlink_profile_removes_generated_acl(self):
        profile = self._view_only_profile(users=self.user)
        access = self.env['ir.model.access'].sudo().search([
            ('name', '=like', 'access.profile.%s.%%' % profile.id),
        ])
        self.assertTrue(access)
        group = profile.generated_group_id
        profile.unlink()
        self.assertFalse(access.exists())
        self.assertFalse(group.exists())

    def test_company_scope_skips_other_company(self):
        company_b = self.env['res.company'].create({'name': 'BAM Company B'})
        self.user.write({'company_ids': [(4, company_b.id)]})
        self._view_only_profile(users=self.user, extra={
            'company_ids': [(6, 0, [company_b.id])],
        })
        self.assertFalse(
            self.Rule.with_user(self.user)._is_blocked('res.partner', 'create'),
            'Restrictions must not apply in the default company',
        )
        self.assertTrue(
            self.Rule.with_user(self.user).with_company(company_b)._is_blocked(
                'res.partner', 'create'),
        )

    def test_simulator_assign_profile(self):
        profile = self.Profile.create({'name': 'Sim Profile'})
        wizard = self.env['access.profile.simulator'].create({
            'user_id': self.user.id,
            'profile_id': profile.id,
        })
        wizard.action_refresh()
        wizard.action_assign_profile()
        self.assertIn(self.user, profile.user_ids)
        self.assertIn(self.user, profile.generated_group_id.users)

    def test_record_rule_own_documents(self):
        profile = self.Profile.create({
            'name': 'Own documents',
            'user_ids': [(6, 0, [self.user.id])],
            'model_line_ids': [(0, 0, {
                'model_id': self.partner_model.id,
                'perm_read': True,
                'perm_write': True,
                'perm_create': True,
                'perm_unlink': True,
                'record_rule_preset': 'own_documents',
            })],
        })
        domain = profile.model_line_ids[:1]._record_rule_domain()
        self.assertTrue(domain)
        rule = self.env['ir.rule'].sudo().search([
            ('name', '=', profile._rule_name('res.partner')),
        ], limit=1)
        self.assertTrue(rule, domain)
        self.assertEqual(rule.domain_force, domain)

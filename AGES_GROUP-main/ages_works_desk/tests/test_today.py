# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWorksToday(TransactionCase):

    def test_today_empty_company_scope(self):
        payload = self.env['ages.works.desk'].get_today({'company_ids': [0]})
        self.assertTrue(payload.get('ok'))
        self.assertIn('queues', payload)
        self.assertIsInstance(payload['queues'], list)
        for queue in payload['queues']:
            self.assertIn('key', queue)
            self.assertIn('label', queue)
            self.assertIn('count', queue)
            self.assertEqual(queue['count'], 0)
            self.assertIn(queue.get('severity'), ('normal', 'warning', 'danger'))

    def test_today_optional_model_missing(self):
        desk = self.env['ages.works.desk']
        self.assertFalse(desk._works_can_read('ages.model.that.does.not.exist'))
        self.assertFalse(desk._works_model_exists('ages.model.that.does.not.exist'))
        payload = desk.get_today({})
        self.assertTrue(payload.get('ok'))
        self.assertIn('queues', payload)
        self.assertIn('features', payload)

    def test_today_optional_field_missing(self):
        desk = self.env['ages.works.desk']
        self.assertFalse(desk._works_has_field('ages.contract', 'not_a_real_field'))
        payload = desk.get_site({})
        self.assertTrue(payload.get('ok'))
        spend = desk.get_spend({})
        self.assertTrue(spend.get('ok'))
        books = desk.get_books({})
        self.assertTrue(books.get('ok'))

    def test_today_normal_user_access(self):
        user = self.env['res.users'].create({
            'name': 'Works Desk User',
            'login': 'ages_works_desk_user',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('project.group_project_user').id,
                self.env.ref('account.group_account_readonly').id,
            ])],
        })
        payload = self.env['ages.works.desk'].with_user(user).get_today({})
        self.assertTrue(payload.get('ok'))
        self.assertIn('queues', payload)
        self.assertNotEqual(user.id, 1)

    def test_filter_options_include_contracts(self):
        options = self.env['ages.works.desk'].get_filter_options({})
        self.assertIn('companies', options)
        self.assertIn('contracts', options)
        self.assertIn('projects', options)
        for screen in ('get_today', 'get_contracts', 'get_site', 'get_spend', 'get_books'):
            payload = getattr(self.env['ages.works.desk'], screen)({})
            self.assertTrue(payload.get('ok'), screen)

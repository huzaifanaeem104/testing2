# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    quality_check_ids = fields.One2many('quality.check', 'picking_id')
    quality_check_todo = fields.Integer(compute='_compute_quality_check_status')
    quality_check_fail = fields.Integer(compute='_compute_quality_check_status')
    quality_check_count = fields.Integer(compute='_compute_quality_check_status')

    @api.depends('quality_check_ids.quality_state')
    def _compute_quality_check_status(self):
        for picking in self:
            checks = picking.quality_check_ids
            picking.quality_check_count = len(checks)
            picking.quality_check_todo = len(checks.filtered(lambda check: check.quality_state == 'none'))
            picking.quality_check_fail = len(checks.filtered(lambda check: check.quality_state == 'fail'))

    def action_confirm(self):
        res = super().action_confirm()
        self._generate_quality_checks()
        return res

    def _generate_quality_checks(self):
        Check = self.env['quality.check']
        for picking in self:
            points = self.env['quality.point'].search([
                ('picking_type_ids', 'in', picking.picking_type_id.id),
                ('company_id', '=', picking.company_id.id),
            ])
            products = picking.move_ids.mapped('product_id')
            existing = {(check.point_id.id, check.product_id.id) for check in picking.quality_check_ids}
            for point in points:
                for product in products:
                    if not point._applies_to_product(product):
                        continue
                    if (point.id, product.id) in existing:
                        continue
                    Check.create({
                        'point_id': point.id,
                        'product_id': product.id,
                        'picking_id': picking.id,
                        'company_id': picking.company_id.id,
                        'team_id': point.team_id.id,
                        'test_type_id': point.test_type_id.id,
                    })

    def _pre_action_done_hook(self):
        res = super()._pre_action_done_hook()
        if res is not True:
            return res
        pending = self.mapped('quality_check_ids').filtered(lambda check: check.quality_state == 'none')
        if pending and not self.env.context.get('skip_quality_check'):
            return {
                'type': 'ir.actions.act_window',
                'name': _('Quality Checks'),
                'res_model': 'quality.check.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_picking_id': self[:1].id,
                    'default_check_ids': pending.ids,
                },
            }
        failed = self.mapped('quality_check_ids').filtered(lambda check: check.quality_state == 'fail')
        if failed:
            raise UserError(_(
                'Quality checks failed on %s. Resolve the alerts or pass the checks before validating.',
                ', '.join(failed.mapped('picking_id.name')),
            ))
        return res

    def action_open_quality_checks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quality Checks'),
            'res_model': 'quality.check',
            'view_mode': 'list,form',
            'domain': [('picking_id', '=', self.id)],
            'context': {'default_picking_id': self.id},
        }

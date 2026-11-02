# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QualityCheckWizard(models.TransientModel):
    _name = 'quality.check.wizard'
    _description = 'Quality Check Wizard'

    picking_id = fields.Many2one('stock.picking', required=True)
    check_ids = fields.Many2many('quality.check')
    current_check_id = fields.Many2one('quality.check')
    title = fields.Char(related='current_check_id.title')
    product_id = fields.Many2one(related='current_check_id.product_id')
    note = fields.Html(related='current_check_id.note')
    test_type = fields.Char(related='current_check_id.test_type')
    measure = fields.Float()
    additional_note = fields.Text()
    remaining = fields.Integer(compute='_compute_remaining')

    @api.depends('check_ids.quality_state')
    def _compute_remaining(self):
        for wizard in self:
            wizard.remaining = len(wizard.check_ids.filtered(lambda check: check.quality_state == 'none'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env['stock.picking'].browse(res.get('picking_id') or self.env.context.get('default_picking_id'))
        checks = self.env['quality.check'].browse(self.env.context.get('default_check_ids') or [])
        if picking and not checks:
            checks = picking.quality_check_ids.filtered(lambda check: check.quality_state == 'none')
        res['picking_id'] = picking.id
        res['check_ids'] = [(6, 0, checks.ids)]
        res['current_check_id'] = checks[:1].id
        return res

    def _advance(self):
        remaining = self.check_ids.filtered(lambda check: check.quality_state == 'none')
        if remaining:
            self.current_check_id = remaining[:1]
            self.measure = 0.0
            self.additional_note = False
            return self._reopen()
        if self.check_ids.filtered(lambda check: check.quality_state == 'fail'):
            return {'type': 'ir.actions.act_window_close'}
        return self.picking_id.with_context(skip_quality_check=True).button_validate()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_pass(self):
        self.ensure_one()
        if not self.current_check_id:
            raise UserError(_('There is no quality check to process.'))
        if self.current_check_id.test_type == 'measure':
            point = self.current_check_id.point_id
            self.current_check_id.measure = self.measure
            if point.measure_min or point.measure_max:
                if self.measure < point.measure_min or self.measure > point.measure_max:
                    self.current_check_id.additional_note = self.additional_note
                    self.current_check_id.do_fail()
                    return self._advance()
        self.current_check_id.additional_note = self.additional_note
        self.current_check_id.do_pass()
        return self._advance()

    def action_fail(self):
        self.ensure_one()
        if not self.current_check_id:
            raise UserError(_('There is no quality check to process.'))
        self.current_check_id.additional_note = self.additional_note
        self.current_check_id.measure = self.measure
        self.current_check_id.do_fail()
        return self._advance()

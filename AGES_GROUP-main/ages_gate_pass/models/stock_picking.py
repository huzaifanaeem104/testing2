# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


_WIZARD_SETUP_DONE = False


def _ensure_receipt_wizard_setup(env):
    global _WIZARD_SETUP_DONE
    if _WIZARD_SETUP_DONE:
        return
    env.cr.execute("""
        CREATE TABLE IF NOT EXISTS ages_receipt_validation_wizard (
            id SERIAL PRIMARY KEY,
            picking_id INTEGER,
            location_dest_id INTEGER,
            create_uid INTEGER,
            create_date TIMESTAMP WITHOUT TIME ZONE,
            write_uid INTEGER,
            write_date TIMESTAMP WITHOUT TIME ZONE
        );
    """)
    model_rec = env['ir.model'].sudo().search([('model', '=', 'ages.receipt.validation.wizard')], limit=1)
    if not model_rec:
        model_rec = env['ir.model'].sudo().create({
            'name': 'Confirm Receipt Destination Location',
            'model': 'ages.receipt.validation.wizard',
            'state': 'base',
        })
    access_rec = env['ir.model.access'].sudo().search([('model_id', '=', model_rec.id)], limit=1)
    if not access_rec:
        env['ir.model.access'].sudo().create({
            'name': 'access_ages_receipt_validation_wizard',
            'model_id': model_rec.id,
            'perm_read': True,
            'perm_write': True,
            'perm_create': True,
            'perm_unlink': True,
        })
    view_rec = env.ref('ages_gate_pass.view_ages_receipt_validation_wizard_form', raise_if_not_found=False)
    if not view_rec:
        view_rec = env['ir.ui.view'].sudo().search([
            ('model', '=', 'ages.receipt.validation.wizard'),
            ('type', '=', 'form'),
        ], limit=1)
    if not view_rec:
        view_arch = """
            <form string="Confirm Destination Location">
                <div class="alert alert-info" role="alert">
                    You are validating this receipt with the Destination Location specified below.
                    If you want to change it, select a new Destination Location, otherwise click <strong>Validate</strong> to proceed.
                </div>
                <group>
                    <field name="picking_id" readonly="1"/>
                    <field name="location_dest_id" options="{'no_create': True}"/>
                </group>
                <footer>
                    <button string="Validate" name="action_validate" type="object" class="btn-primary"/>
                    <button string="Cancel" class="btn-secondary" special="cancel"/>
                </footer>
            </form>
        """
        env['ir.ui.view'].sudo().create({
            'name': 'ages.receipt.validation.wizard.form',
            'model': 'ages.receipt.validation.wizard',
            'type': 'form',
            'arch': view_arch,
        })
    _WIZARD_SETUP_DONE = True


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    gate_pass_ids = fields.Many2many(
        comodel_name='ages.gate.pass',
        relation='stock_picking_ages_gate_pass_rel',
        column1='picking_id',
        column2='gate_pass_id',
        string='Gate Passes',
        copy=False,
        check_company=True,
    )
    gate_pass_id = fields.Many2one(
        comodel_name='ages.gate.pass',
        string='Gate Pass',
        copy=False,
        check_company=True,
        help='Primary Gate Pass for this GRN.',
    )
    gate_pass_count = fields.Integer(
        string='Gate Pass Count',
        compute='_compute_gate_pass_count',
    )

    def button_validate(self):
        if not self.env.context.get('skip_location_check_wizard'):
            for picking in self:
                if picking.picking_type_code == 'incoming':
                    _ensure_receipt_wizard_setup(self.env)
                    wizard = self.env['ages.receipt.validation.wizard'].sudo().create({
                        'picking_id': picking.id,
                        'location_dest_id': picking.location_dest_id.id if picking.location_dest_id else False,
                    })
                    return {
                        'name': _('Confirm Destination Location'),
                        'type': 'ir.actions.act_window',
                        'res_model': 'ages.receipt.validation.wizard',
                        'res_id': wizard.id,
                        'view_mode': 'form',
                        'target': 'new',
                    }
        return super().button_validate()
        return super().button_validate()

    @api.depends('gate_pass_ids')
    def _compute_gate_pass_count(self):
        for picking in self:
            picking.gate_pass_count = len(picking.gate_pass_ids)

    def write(self, vals):
        res = super().write(vals)
        if 'gate_pass_ids' in vals:
            for picking in self:
                for gate_pass in picking.gate_pass_ids:
                    if not gate_pass.picking_id:
                        gate_pass.with_context(skip_gate_pass_edit_consume=True).write({
                            'picking_id': picking.id,
                        })
                if not picking.gate_pass_id and picking.gate_pass_ids:
                    picking.gate_pass_id = picking.gate_pass_ids[:1]
        return res

    def action_view_gate_passes(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Gate Pass'),
            'res_model': 'ages.gate.pass',
            'view_mode': 'list,form',
            'domain': [
                '|',
                ('picking_id', '=', self.id),
                ('id', 'in', self.gate_pass_ids.ids),
            ],
            'context': {
                'default_picking_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
                'default_gate_type': 'in' if self.picking_type_code == 'incoming' else 'out',
            },
        }
        passes = self.gate_pass_ids | self.env['ages.gate.pass'].search([('picking_id', '=', self.id)])
        if len(passes) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': passes.id,
            })
        return action

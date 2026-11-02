# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QualityPointTestType(models.Model):
    _name = 'quality.point.test_type'
    _description = 'Quality Control Test Type'

    name = fields.Char(required=True, translate=True)
    technical_name = fields.Char(required=True)
    active = fields.Boolean(default=True)


class QualityAlertTeam(models.Model):
    _name = 'quality.alert.team'
    _description = 'Quality Team'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', index=True)
    sequence = fields.Integer(default=10)
    check_count = fields.Integer(compute='_compute_counts')
    alert_count = fields.Integer(compute='_compute_counts')

    def _compute_counts(self):
        checks = self.env['quality.check']._read_group(
            [('team_id', 'in', self.ids), ('quality_state', '=', 'none')],
            ['team_id'],
            ['__count'],
        )
        alerts = self.env['quality.alert']._read_group(
            [('team_id', 'in', self.ids), ('stage_id.done', '=', False)],
            ['team_id'],
            ['__count'],
        )
        check_map = {team.id: count for team, count in checks}
        alert_map = {team.id: count for team, count in alerts}
        for team in self:
            team.check_count = check_map.get(team.id, 0)
            team.alert_count = alert_map.get(team.id, 0)

    @api.model
    def _get_quality_team(self, company=None):
        company = company or self.env.company
        team = self.search([
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)
        if not team:
            raise UserError(_('Create a quality team in Inventory → Quality first.'))
        return team


class QualityPoint(models.Model):
    _name = 'quality.point'
    _description = 'Quality Control Point'
    _inherit = ['mail.thread']
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(default=lambda self: _('New'), copy=False, required=True)
    sequence = fields.Integer(default=10)
    title = fields.Char()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company,
    )
    team_id = fields.Many2one(
        'quality.alert.team', required=True, check_company=True,
        default=lambda self: self.env['quality.alert.team'].search([], limit=1),
    )
    product_ids = fields.Many2many('product.product', string='Products', check_company=True)
    product_category_ids = fields.Many2many('product.category', string='Product Categories')
    picking_type_ids = fields.Many2many(
        'stock.picking.type', string='Operation Types', required=True, check_company=True,
    )
    test_type_id = fields.Many2one(
        'quality.point.test_type', string='Test Type', required=True, tracking=True,
        default=lambda self: self.env['quality.point.test_type'].search([], limit=1),
    )
    test_type = fields.Char(related='test_type_id.technical_name', store=True)
    note = fields.Html()
    measure_min = fields.Float('Min')
    measure_max = fields.Float('Max')
    check_count = fields.Integer(compute='_compute_check_count')
    check_ids = fields.One2many('quality.check', 'point_id')

    def _compute_check_count(self):
        data = self.env['quality.check']._read_group(
            [('point_id', 'in', self.ids)], ['point_id'], ['__count'],
        )
        counts = {point.id: count for point, count in data}
        for point in self:
            point.check_count = counts.get(point.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('quality.point') or _('New')
        return super().create(vals_list)

    def _applies_to_product(self, product):
        self.ensure_one()
        if not self.product_ids and not self.product_category_ids:
            return True
        if product in self.product_ids:
            return True
        return product.categ_id in self.product_category_ids


class QualityCheck(models.Model):
    _name = 'quality.check'
    _description = 'Quality Check'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default=lambda self: _('New'), copy=False)
    title = fields.Char()
    point_id = fields.Many2one('quality.point', check_company=True)
    quality_state = fields.Selection(
        [('none', 'To Do'), ('pass', 'Passed'), ('fail', 'Failed')],
        default='none',
        tracking=True,
        copy=False,
    )
    control_date = fields.Datetime(copy=False)
    product_id = fields.Many2one('product.product', check_company=True)
    picking_id = fields.Many2one('stock.picking', check_company=True)
    user_id = fields.Many2one('res.users', tracking=True)
    team_id = fields.Many2one('quality.alert.team', required=True, check_company=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company,
    )
    test_type_id = fields.Many2one('quality.point.test_type', required=True)
    test_type = fields.Char(related='test_type_id.technical_name')
    note = fields.Html()
    additional_note = fields.Text()
    measure = fields.Float()
    picture = fields.Binary(attachment=True)
    alert_ids = fields.One2many('quality.alert', 'check_id')
    alert_count = fields.Integer(compute='_compute_alert_count')

    def _compute_alert_count(self):
        data = self.env['quality.alert']._read_group(
            [('check_id', 'in', self.ids)], ['check_id'], ['__count'],
        )
        counts = {check.id: count for check, count in data}
        for check in self:
            check.alert_count = counts.get(check.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('quality.check') or _('New')
            point = self.env['quality.point'].browse(vals.get('point_id'))
            if point:
                vals.setdefault('test_type_id', point.test_type_id.id)
                vals.setdefault('team_id', point.team_id.id)
                vals.setdefault('title', point.title or point.name)
                vals.setdefault('note', point.note)
        return super().create(vals_list)

    def do_pass(self):
        self.write({
            'quality_state': 'pass',
            'user_id': self.env.user.id,
            'control_date': fields.Datetime.now(),
        })

    def do_fail(self):
        self.write({
            'quality_state': 'fail',
            'user_id': self.env.user.id,
            'control_date': fields.Datetime.now(),
        })
        alerts = self.env['quality.alert']
        for check in self:
            alerts |= self.env['quality.alert'].create({
                'name': _('Quality failure: %s', check.display_name),
                'check_id': check.id,
                'picking_id': check.picking_id.id,
                'product_id': check.product_id.id,
                'team_id': check.team_id.id,
                'company_id': check.company_id.id,
                'description': check.additional_note or check.note,
            })
        return alerts

    def action_open_alerts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quality Alerts'),
            'res_model': 'quality.alert',
            'view_mode': 'list,form',
            'domain': [('check_id', '=', self.id)],
            'context': {'default_check_id': self.id, 'default_team_id': self.team_id.id},
        }


class QualityAlertStage(models.Model):
    _name = 'quality.alert.stage'
    _description = 'Quality Alert Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    folded = fields.Boolean()
    done = fields.Boolean('Processed')


class QualityAlert(models.Model):
    _name = 'quality.alert'
    _description = 'Quality Alert'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default=lambda self: _('New'), copy=False)
    description = fields.Html()
    stage_id = fields.Many2one(
        'quality.alert.stage',
        default=lambda self: self.env['quality.alert.stage'].search([], limit=1),
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company,
    )
    team_id = fields.Many2one('quality.alert.team', required=True, check_company=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, tracking=True)
    picking_id = fields.Many2one('stock.picking', check_company=True)
    check_id = fields.Many2one('quality.check', check_company=True)
    product_id = fields.Many2one('product.product', check_company=True)
    action_corrective = fields.Html()
    action_preventive = fields.Html()
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Very High'),
    ], default='0')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('quality.alert') or _('New')
        return super().create(vals_list)

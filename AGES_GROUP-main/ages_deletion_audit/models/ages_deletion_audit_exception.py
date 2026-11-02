# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .constants import BUSINESS_MODULE_SELECTION


class AgesDeletionAuditException(models.Model):
    _name = 'ages.deletion.audit.exception'
    _description = 'Deletion Audit Exception'
    _order = 'model_name'

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Model',
        required=True,
        ondelete='cascade',
        index=True,
    )
    model_name = fields.Char(
        related='model_id.model',
        string='Technical Name',
        store=True,
        index=True,
        readonly=True,
    )
    action = fields.Selection(
        selection=[
            ('include', 'Always Audit'),
            ('exclude', 'Never Audit'),
        ],
        string='Action',
        required=True,
        default='exclude',
    )
    business_module = fields.Selection(
        selection=BUSINESS_MODULE_SELECTION,
        string='Business Module',
        help='Required when forcing a model into the audit. Ignored for exclusions.',
    )
    note = fields.Char(string='Note')

    _sql_constraints = [
        (
            'model_uniq',
            'unique(model_id)',
            'An exception already exists for this model.',
        ),
    ]

    def _ages_invalidate(self):
        self.env['ages.deletion.audit']._ages_clear_area_cache()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ages_invalidate()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ages_invalidate()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['ages.deletion.audit']._ages_clear_area_cache()
        return res

# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _ages_header_analytic_account(self):
        """Analytic from the parent bill/invoice/JE header (project analytic)."""
        move = self.move_id
        if not move and self.env.context.get('default_move_id'):
            move = self.env['account.move'].browse(self.env.context['default_move_id'])
        if not move or 'ages_analytic_account_id' not in move._fields:
            return self.env['account.analytic.account']
        return (
            move.ages_analytic_account_id
            or (move.ages_project_id.account_id if move.ages_project_id else self.env['account.analytic.account'])
        )

    def _ages_header_analytic_distribution(self):
        analytic = self._ages_header_analytic_account()
        if not analytic:
            return {}
        return {str(analytic.id): 100}

    def _related_analytic_distribution(self):
        vals = super()._related_analytic_distribution() or {}
        header = self._ages_header_analytic_distribution()
        if header:
            vals = dict(vals, **header)
        return vals

    @api.depends(
        'move_id.ages_analytic_account_id',
        'move_id.ages_project_id',
        'move_id.ages_project_id.account_id',
    )
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        # Invoice tax/payment-term lines skip the core compute; still stamp header analytic
        # on product lines that came out empty (no distribution model).
        for line in self:
            if line.display_type in ('line_section', 'line_note'):
                continue
            if line.analytic_distribution:
                continue
            # Posted invoices: do not dirty line_ids on open (that snaps the
            # notebook back to Journal Items).
            if line.move_id and line.move_id.state != 'draft':
                continue
            header = line._ages_header_analytic_distribution()
            if header:
                line.analytic_distribution = header

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        dist = self._ages_header_analytic_distribution()
        if dist and (not fields_list or 'analytic_distribution' in fields_list):
            defaults.setdefault('analytic_distribution', dist)
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        Move = self.env['account.move']
        for vals in vals_list:
            if vals.get('analytic_distribution') or vals.get('display_type') in ('line_section', 'line_note'):
                continue
            move_id = vals.get('move_id') or self.env.context.get('default_move_id')
            if not move_id:
                continue
            move = Move.browse(move_id)
            analytic = (
                move.ages_analytic_account_id
                if 'ages_analytic_account_id' in move._fields
                else False
            ) or (
                move.ages_project_id.account_id
                if 'ages_project_id' in move._fields and move.ages_project_id
                else False
            )
            if analytic:
                vals['analytic_distribution'] = {str(analytic.id): 100}
        return super().create(vals_list)

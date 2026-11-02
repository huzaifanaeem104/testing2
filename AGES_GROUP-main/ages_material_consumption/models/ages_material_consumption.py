# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class AgesMaterialConsumption(models.Model):
    _name = 'ages.material.consumption'
    _description = 'Material Consumption'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Material Consumption No.',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
        index=True,
    )
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        required=True,
        tracking=True,
        index=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        compute='_compute_from_project',
        store=True,
        readonly=True,
    )
    contract_id = fields.Many2one(
        comodel_name='ages.contract',
        string='Contract',
        compute='_compute_from_project',
        store=True,
        readonly=True,
        index=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    source_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Source Location',
        required=True,
        tracking=True,
        domain="[('usage', '=', 'internal'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    destination_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Destination Location',
        required=True,
        tracking=True,
        domain="[('usage', '=', 'view'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Locations with type View (as per Inventory specification).',
    )
    reference = fields.Char(string='Reference', tracking=True)
    sub_company_id = fields.Many2one(
        comodel_name='ages.sub.company',
        string='Active Company',
        compute='_compute_from_project',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name='ages.material.consumption.line',
        inverse_name='consumption_id',
        string='Lines',
        copy=True,
    )
    quantity_total = fields.Float(
        string='Quantity to Consume',
        compute='_compute_totals',
        store=True,
        digits='Product Unit of Measure',
    )
    qty_returned_total = fields.Float(
        string='Quantity Return',
        compute='_compute_totals',
        store=True,
        digits='Product Unit of Measure',
    )
    amount_total = fields.Monetary(
        string='Total Amount',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Journal Entry',
        copy=False,
        readonly=True,
    )
    move_state = fields.Selection(
        related='move_id.state',
        string='JE Status',
        store=True,
    )
    stock_move_ids = fields.One2many(
        comodel_name='stock.move',
        inverse_name='ages_material_consumption_id',
        string='Stock Moves',
        copy=False,
        readonly=True,
    )
    stock_move_count = fields.Integer(
        string='Stock Moves Count',
        compute='_compute_stock_move_count',
    )
    can_return = fields.Boolean(
        string='Can Return',
        compute='_compute_can_return',
    )

    # -------------------------------------------------------------------------
    # Computes / onchange
    # -------------------------------------------------------------------------
    @api.depends('stock_move_ids')
    def _compute_stock_move_count(self):
        for rec in self:
            rec.stock_move_count = len(rec.stock_move_ids)

    @api.depends('state', 'line_ids.quantity', 'line_ids.qty_returned')
    def _compute_can_return(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for rec in self:
            rec.can_return = (
                rec.state == 'done'
                and any(
                    float_compare(line.quantity - line.qty_returned, 0.0, precision_digits=precision) > 0
                    for line in rec.line_ids
                )
            )

    @api.depends(
        'project_id',
        'project_id.account_id',
        'project_id.ages_contract_id',
        'project_id.ages_contract_id.sub_company_id',
        'project_id.company_id',
    )
    def _compute_from_project(self):
        for rec in self:
            project = rec.project_id
            rec.analytic_account_id = project.account_id if project else False
            rec.contract_id = project.ages_contract_id if project else False
            rec.sub_company_id = (
                project.ages_contract_id.sub_company_id
                if project and project.ages_contract_id
                else False
            )

    @api.depends('line_ids.quantity', 'line_ids.qty_returned', 'line_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.quantity_total = sum(rec.line_ids.mapped('quantity'))
            rec.qty_returned_total = sum(rec.line_ids.mapped('qty_returned'))
            rec.amount_total = sum(rec.line_ids.mapped('amount'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if not self.project_id:
            return
        project = self.project_id
        if project.company_id:
            self.company_id = project.company_id
        # Default source = project-linked location (changeable)
        if project.ages_location_id:
            self.source_location_id = project.ages_location_id
        elif project.ages_contract_id and project.ages_contract_id.location_id:
            self.source_location_id = project.ages_contract_id.location_id
        # Default destination = company default parent location (view)
        parent = project.company_id.ages_default_parent_location_id if project.company_id else False
        if not parent:
            parent = self.company_id.ages_default_parent_location_id
        if parent and parent.usage == 'view':
            self.destination_location_id = parent

    @api.onchange('source_location_id')
    def _onchange_source_location_id(self):
        """Refresh Available qty on lines when source location changes."""
        for line in self.line_ids:
            line._compute_available_qty()

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) in (_('New'), 'New', False):
                vals['name'] = sequence.next_by_code('ages.material.consumption') or _('New')
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_(
                    'You cannot delete a Done Material Consumption (%s).',
                    rec.display_name,
                ))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft records can be confirmed.'))
            rec._check_lines_ready()
            rec.state = 'confirmed'
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft records can be cancelled.'))
            rec.state = 'cancelled'
        return True

    def action_draft(self):
        """Set Confirmed or Cancelled records back to Draft."""
        for rec in self:
            if rec.state not in ('confirmed', 'cancelled'):
                raise UserError(_('Only Confirmed or Cancelled records can be set back to Draft.'))
            if rec.state == 'done' or rec.stock_move_ids or rec.move_id:
                raise UserError(_(
                    'You cannot set %s back to Draft because it already has stock moves or a journal entry.',
                    rec.display_name,
                ))
            rec.state = 'draft'
        return True

    def action_validate(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Only Confirmed records can be validated.'))
            rec._check_lines_ready(check_availability=True)
            stock_moves = rec._create_stock_moves()
            move = rec._create_and_post_journal_entry()
            rec.write({
                'state': 'done',
                'move_id': move.id,
                'stock_move_ids': [Command.set(stock_moves.ids)],
            })
        return True

    def action_return(self):
        """Open return wizard (qty per product), same idea as delivery return."""
        self.ensure_one()
        if not self.can_return:
            raise UserError(_('There is nothing left to return on this Material Consumption.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return'),
            'res_model': 'ages.material.consumption.return',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': 'ages.material.consumption',
                'default_consumption_id': self.id,
            },
        }

    def action_view_journal_entry(self):
        self.ensure_one()
        moves = self.env['account.move'].search([
            ('ages_material_consumption_id', '=', self.id),
        ])
        if not moves and self.move_id:
            moves = self.move_id
        if not moves:
            return False
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'target': 'current',
            'domain': [('id', 'in', moves.ids)],
        }
        if len(moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': moves.id,
            })
        else:
            action['view_mode'] = 'list,form'
        return action

    def action_view_stock_moves(self):
        self.ensure_one()
        moves = self.stock_move_ids
        if not moves:
            return False
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Stock Moves'),
            'res_model': 'stock.move',
            'target': 'current',
            'domain': [('id', 'in', moves.ids)],
        }
        if len(moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': moves.id,
            })
        else:
            action['view_mode'] = 'list,form'
        return action

    def _check_lines_ready(self, check_availability=False):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('Project is required.'))
        if not self.source_location_id:
            raise UserError(_('Source Location is required.'))
        if not self.destination_location_id:
            raise UserError(_('Destination Location is required.'))
        if not self.line_ids:
            raise UserError(_('Please add at least one product line.'))
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self.line_ids:
            if not line.product_id:
                raise UserError(_('Product is required on every line.'))
            if float_is_zero(line.quantity, precision_digits=precision):
                raise UserError(_(
                    'Quantity to Consume must be greater than zero for product %s.',
                    line.product_id.display_name,
                ))
            if check_availability:
                # Refresh available before comparing
                line._compute_available_qty()
                if float_compare(line.quantity, line.available_qty, precision_digits=precision) > 0:
                    raise UserError(_(
                        'Insufficient quantity for %(product)s in %(location)s.\n'
                        'Available: %(available)s, Requested: %(requested)s',
                        product=line.product_id.display_name,
                        location=self.source_location_id.display_name,
                        available=line.available_qty,
                        requested=line.quantity,
                    ))

    # -------------------------------------------------------------------------
    # Stock moves (consume from source into inventory location under destination view)
    # -------------------------------------------------------------------------
    def _get_consumption_dest_location(self):
        """Return (or create) an inventory location under the selected View destination.

        Destination on the form is restricted to usage=view per the Inventory
        specification. Stock cannot be moved onto a view location, so consumption
        physically lands in a child inventory location.
        """
        self.ensure_one()
        parent = self.destination_location_id
        Location = self.env['stock.location']
        loc = Location.search([
            ('location_id', '=', parent.id),
            ('name', '=', 'Material Consumption'),
            ('usage', '=', 'inventory'),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not loc:
            loc = Location.create({
                'name': 'Material Consumption',
                'usage': 'inventory',
                'location_id': parent.id,
                'company_id': self.company_id.id,
            })
        return loc

    def _create_stock_moves(self):
        self.ensure_one()
        dest = self._get_consumption_dest_location()
        Move = self.env['stock.move']
        moves = Move.browse()
        for line in self.line_ids:
            move = Move.create({
                'name': self.name,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': self.source_location_id.id,
                'location_dest_id': dest.id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'reference': self.reference or self.name,
                'date': fields.Datetime.now(),
                'ages_material_consumption_id': self.id,
            })
            moves |= move
        moves._action_confirm()
        moves._action_assign()
        for move in moves:
            move.quantity = move.product_uom_qty
            move.picked = True
        moves.with_context(force_period_date=self.date)._action_done()
        return moves

    def _create_return_stock_moves(self, return_lines):
        """Create reverse stock moves: consumption location → original source."""
        self.ensure_one()
        dest = self._get_consumption_dest_location()
        Move = self.env['stock.move']
        moves = Move.browse()
        for ret_line in return_lines:
            line = ret_line.consumption_line_id
            origin_move = self.stock_move_ids.filtered(
                lambda m: m.product_id == line.product_id
                and m.location_id == self.source_location_id
                and m.state == 'done'
            )[:1]
            move = Move.create({
                'name': _('Return %s') % self.name,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': ret_line.quantity,
                'location_id': dest.id,
                'location_dest_id': self.source_location_id.id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'reference': _('Return of %s') % (self.reference or self.name),
                'date': fields.Datetime.now(),
                'ages_material_consumption_id': self.id,
                'origin_returned_move_id': origin_move.id if origin_move else False,
            })
            moves |= move
        moves._action_confirm()
        moves._action_assign()
        for move in moves:
            move.quantity = move.product_uom_qty
            move.picked = True
        moves.with_context(force_period_date=self.date)._action_done()
        return moves

    def _create_and_post_return_journal_entry(self, return_lines, stock_moves=None):
        """Post reverse JE: Debit Stock / Credit Expense for returned quantities."""
        self.ensure_one()
        # Clean auto valuation JEs created by stock_account for these return moves
        recent_return_moves = stock_moves or self.env['stock.move']
        svls = recent_return_moves.stock_valuation_layer_ids
        auto_moves = svls.account_move_id
        if svls:
            svls.write({'account_move_id': False})
        for am in auto_moves.filtered(lambda m: m.state == 'posted'):
            am.button_draft()
        if auto_moves:
            auto_moves.with_context(force_delete=True).unlink()

        analytic_dist = {}
        if self.analytic_account_id:
            analytic_dist = {str(self.analytic_account_id.id): 100}

        first_product = return_lines[0].product_id
        journal = self._get_stock_journal(first_product)
        line_commands = []
        for ret_line in return_lines:
            line = ret_line.consumption_line_id
            amount = (ret_line.quantity or 0.0) * (line.unit_cost or 0.0)
            if float_is_zero(amount, precision_rounding=self.currency_id.rounding):
                continue
            stock_account, expense_account = self._get_line_accounts(line.product_id)
            label = _(
                'Return %(consumption)s - %(product)s',
                consumption=self.name,
                product=line.product_id.display_name,
            )
            # Reverse of original: Debit Stock / Credit Expense
            line_commands.append(Command.create({
                'name': label,
                'account_id': stock_account.id,
                'debit': amount,
                'credit': 0.0,
                'analytic_distribution': analytic_dist or False,
                'product_id': line.product_id.id,
                'quantity': ret_line.quantity,
                'product_uom_id': line.uom_id.id,
            }))
            line_commands.append(Command.create({
                'name': label,
                'account_id': expense_account.id,
                'debit': 0.0,
                'credit': amount,
                'analytic_distribution': analytic_dist or False,
                'product_id': line.product_id.id,
                'quantity': ret_line.quantity,
                'product_uom_id': line.uom_id.id,
            }))

        if not line_commands:
            raise UserError(_('Cannot return: total return amount is zero.'))

        move = self.env['account.move'].with_company(self.company_id).create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': _('Return of %s') % (self.reference or self.name),
            'company_id': self.company_id.id,
            'ages_material_consumption_id': self.id,
            'ages_contract_id': self.contract_id.id if self.contract_id else False,
            'ages_project_id': self.project_id.id,
            'ages_sub_company_id': self.sub_company_id.id if self.sub_company_id else False,
            'line_ids': line_commands,
        })
        move.action_post()
        if svls:
            svls.write({'account_move_id': move.id})
        return move

    # -------------------------------------------------------------------------
    # Journal entry (Stock Valuation journal)
    # -------------------------------------------------------------------------
    def _get_stock_journal(self, product):
        self.ensure_one()
        accounts = product.product_tmpl_id.with_company(self.company_id).get_product_accounts()
        journal = accounts.get('stock_journal')
        if journal:
            return journal
        journal = self.env['account.journal'].search([
            ('code', '=', 'STJ'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].search([
                ('name', 'ilike', 'Stock Valuation'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        if not journal:
            raise UserError(_(
                'Stock Valuation journal is not configured on the product category '
                'of %s. Set it under Product Category → Inventory Valuation.',
                product.display_name,
            ))
        return journal

    def _get_line_accounts(self, product):
        self.ensure_one()
        product = product.with_company(self.company_id)
        accounts = product.product_tmpl_id.get_product_accounts()
        stock_account = accounts.get('stock_valuation')
        expense_account = accounts.get('expense')
        if not stock_account:
            raise UserError(_(
                'Stock account is not set on the product category of %s '
                '(Product Category → Stock Valuation Account).',
                product.display_name,
            ))
        if not expense_account:
            raise UserError(_(
                'Expense account is not set on the product category of %s '
                '(Product Category → Expense Account).',
                product.display_name,
            ))
        return stock_account, expense_account

    def _create_and_post_journal_entry(self):
        self.ensure_one()
        if self.move_id:
            raise UserError(_('A journal entry is already linked to this Material Consumption.'))

        # Replace any auto-generated stock_account journal entries so we post
        # exactly one JE matching the specification (Expense debit / Stock
        # credit + analytics on all lines).
        pending_moves = self.env['stock.move'].search([
            ('ages_material_consumption_id', '=', self.id),
        ])
        svls = pending_moves.stock_valuation_layer_ids
        auto_moves = svls.account_move_id
        if svls:
            svls.write({'account_move_id': False})
        for am in auto_moves.filtered(lambda m: m.state == 'posted'):
            am.button_draft()
        if auto_moves:
            auto_moves.with_context(force_delete=True).unlink()

        analytic_dist = {}
        if self.analytic_account_id:
            analytic_dist = {str(self.analytic_account_id.id): 100}

        # One journal from the first product; all lines must share a usable journal
        first_product = self.line_ids[0].product_id
        journal = self._get_stock_journal(first_product)

        line_commands = []
        for line in self.line_ids:
            if float_is_zero(line.amount, precision_rounding=self.currency_id.rounding):
                continue
            stock_account, expense_account = self._get_line_accounts(line.product_id)
            label = _('%(consumption)s - %(product)s', consumption=self.name, product=line.product_id.display_name)
            # Debit Expense
            line_commands.append(Command.create({
                'name': label,
                'account_id': expense_account.id,
                'debit': line.amount,
                'credit': 0.0,
                'analytic_distribution': analytic_dist or False,
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'product_uom_id': line.uom_id.id,
            }))
            # Credit Stock
            line_commands.append(Command.create({
                'name': label,
                'account_id': stock_account.id,
                'debit': 0.0,
                'credit': line.amount,
                'analytic_distribution': analytic_dist or False,
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'product_uom_id': line.uom_id.id,
            }))

        if not line_commands:
            raise UserError(_('Cannot validate: total amount is zero.'))

        move = self.env['account.move'].with_company(self.company_id).create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.date,
            'ref': self.reference or self.name,
            'company_id': self.company_id.id,
            'ages_material_consumption_id': self.id,
            'ages_contract_id': self.contract_id.id if self.contract_id else False,
            'ages_project_id': self.project_id.id,
            'ages_sub_company_id': self.sub_company_id.id if self.sub_company_id else False,
            'line_ids': line_commands,
        })
        move.action_post()
        if svls:
            svls.write({'account_move_id': move.id})
        return move

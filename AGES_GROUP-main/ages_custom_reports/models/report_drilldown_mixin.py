from odoo import models, fields, api, _
from odoo.osv import expression


class ReportDrilldownMixin(models.AbstractModel):
    _name = 'report.drilldown.mixin'
    _description = 'Shared drill-down actions for AGES reports'

    def _action_open_interactive_general_ledger(
        self,
        account_id,
        date_from=False,
        date_to=False,
        target_move='posted',
        journal_ids=None,
        analytic_account_id=False,
        parent_name=None,
    ):
        if not date_to:
            date_to = fields.Date.context_today(self)
        gl_wizard = self.env['general.ledger.wizard'].create({
            'date_from': date_from or False,
            'date_to': date_to,
            'target_move': target_move,
            'journal_ids': [(6, 0, journal_ids or [])],
            'analytic_account_id': analytic_account_id or False,
            'account_ids': [(6, 0, [account_id])],
            'unfold_all': True,
        })
        action_name = _('General Ledger')
        if parent_name:
            action_name = _('%s / General Ledger', parent_name)
        return {
            'type': 'ir.actions.client',
            'tag': 'ages_general_ledger_report',
            'name': action_name,
            'params': {
                'wizard_id': gl_wizard.id,
                'account_id': account_id,
            },
        }

    def _action_open_journal_entry(self, move_id, move_line_id=None):
        move = self.env['account.move'].browse(move_id)
        if not move.exists():
            return False
        context = dict(self.env.context)
        if move_line_id:
            context['ages_highlight_move_line_id'] = int(move_line_id)
        return {
            'type': 'ir.actions.act_window',
            'name': move.display_name,
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': context,
        }

    def _action_open_journal_items_for_account(
        self,
        account_id,
        date_from=False,
        date_to=False,
        target_move='posted',
    ):
        if not date_to:
            date_to = fields.Date.context_today(self)
        domain = [
            ('account_id', '=', account_id),
            ('date', '<=', date_to),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        account = self.env['account.account'].browse(account_id)
        return {
            'type': 'ir.actions.act_window',
            'name': account.display_name,
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def _action_open_journal_items_for_partner(
        self,
        partner_id,
        date_from=False,
        date_to=False,
        target_move='posted',
        analytic_account_id=False,
    ):
        if not date_to:
            date_to = fields.Date.context_today(self)
        from ..report.report_filter_domains import analytic_reach_domain, partner_reach_domain

        domain = [
            ('date', '<=', date_to),
        ]
        partner_domain = (
            partner_reach_domain(self.env, [partner_id])
            if partner_id
            else [('partner_id', '=', False)]
        )
        domain = expression.AND([domain, partner_domain])
        if date_from:
            domain.append(('date', '>=', date_from))
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        if analytic_account_id:
            analytic_domain = analytic_reach_domain(self.env, [analytic_account_id])
            if analytic_domain:
                domain = expression.AND([domain, analytic_domain])
        partner = self.env['res.partner'].browse(partner_id) if partner_id else False
        name = partner.display_name if partner else _('Journal Items')
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def _action_open_partner(self, partner_id):
        if not partner_id:
            return False
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': partner.display_name,
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def action_open_journal_entry_from_line(self, move_line_id):
        move_line = self.env['account.move.line'].browse(move_line_id)
        if not move_line.exists():
            return False
        return self._action_open_journal_entry(
            move_line.move_id.id,
            move_line.id,
        )

    def _existing_record_ids(self, model_name, ids):
        clean_ids = []
        seen = set()
        for rec_id in ids or []:
            try:
                rec_id = int(rec_id)
            except (TypeError, ValueError):
                continue
            if rec_id and rec_id not in seen:
                seen.add(rec_id)
                clean_ids.append(rec_id)
        if not clean_ids:
            return []
        existing = set(self.env[model_name].search([('id', 'in', clean_ids)]).ids)
        return [rec_id for rec_id in clean_ids if rec_id in existing]

    def _sanitize_x2m_commands(self, model_name, value):
        if not value:
            return [(6, 0, [])]
        if isinstance(value, (list, tuple)) and value and not isinstance(value[0], (list, tuple)):
            return [(6, 0, self._existing_record_ids(model_name, value))]
        commands = []
        for command in value:
            if not isinstance(command, (list, tuple)) or not command:
                commands.append(command)
                continue
            code = command[0]
            if code == 6:
                ids = command[2] if len(command) > 2 else []
                commands.append((6, 0, self._existing_record_ids(model_name, ids)))
            elif code in (3, 4) and len(command) > 1:
                existing = self._existing_record_ids(model_name, [command[1]])
                if existing:
                    commands.append((code, existing[0]) + tuple(command[2:]))
            else:
                commands.append(command)
        return commands

    def _sanitize_relational_vals(self, vals):
        if not vals:
            return vals
        sanitized = dict(vals)
        for field_name, field in self._fields.items():
            if field_name not in sanitized:
                continue
            value = sanitized[field_name]
            if field.type == 'many2one':
                if not value:
                    sanitized[field_name] = False
                    continue
                rec_id = value[0] if isinstance(value, (list, tuple)) else value
                existing = self._existing_record_ids(field.comodel_name, [rec_id])
                sanitized[field_name] = existing[0] if existing else False
            elif field.type == 'many2many':
                sanitized[field_name] = self._sanitize_x2m_commands(
                    field.comodel_name, value
                )
        return sanitized

    @api.model_create_multi
    def create(self, vals_list):
        sanitized = [self._sanitize_relational_vals(vals) for vals in vals_list]
        return super().create(sanitized)

    def write(self, vals):
        return super().write(self._sanitize_relational_vals(vals))

    def _write_filters(self, vals):
        self.ensure_one()
        self.write(vals or {})
        return self.get_filter_values(self.id)

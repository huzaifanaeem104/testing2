from odoo.exceptions import UserError
from odoo.tools import float_compare


def check_valuation_config(env, product, company, consumption_location):
    """Refuse configurations that would expense the same cost twice.

    With automated (real-time) valuation the vendor bill must hit the stock
    interim account (Anglo-Saxon accounting) so that the expense is only
    recognised when the stock is consumed. With periodic valuation the bill
    is the expense and consumption creates no journal entry.
    """
    product = product.with_company(company)
    if not product.is_storable or product.valuation != 'real_time':
        return
    if not company.anglo_saxon_accounting:
        raise UserError(env._(
            '%(product)s uses automated inventory valuation but Anglo-Saxon accounting is disabled for '
            '%(company)s: vendor bills would be expensed and consumption expensed again. Enable Anglo-Saxon '
            'accounting or use periodic valuation on the product category.',
            product=product.display_name, company=company.name))
    if not consumption_location.valuation_in_account_id:
        raise UserError(env._(
            'Set the expense account of location %(location)s (Farm Settings) before posting %(product)s '
            'under automated valuation.', location=consumption_location.display_name, product=product.display_name))
    if consumption_location.valuation_out_account_id != consumption_location.valuation_in_account_id:
        raise UserError(env._(
            'Location %s must use the same incoming and outgoing valuation account so that reversals cancel '
            'the expense. Save the Farm Settings to synchronise them.', consumption_location.display_name))


def check_available(env, product, quantity, uom, location, lot=False):
    """Raise when ``location`` does not hold ``quantity`` (in ``uom``) of ``product``."""
    if not product.is_storable or location.usage != 'internal':
        return
    needed = uom._compute_quantity(quantity, product.uom_id)
    available = env['stock.quant']._get_available_quantity(product, location, lot_id=lot or None, strict=bool(lot))
    if float_compare(available, needed, precision_rounding=product.uom_id.rounding) < 0:
        raise UserError(env._(
            'Not enough %(product)s in %(location)s: %(available)s %(uom)s available, %(needed)s %(uom)s required.',
            product=product.display_name, location=location.display_name,
            available=round(available, 3), needed=round(needed, 3), uom=product.uom_id.name))


def post_stock_move(env, product, quantity, uom, location, location_dest, company, name, origin,
                    lot=False, extra_vals=None):
    """Create and validate a single stock move with an explicit move line.

    The move goes through the standard confirm/done workflow so quants,
    valuation layers and (for real-time valuation) journal entries are
    produced by Odoo itself.
    """
    vals = {
        'name': name,
        'origin': origin,
        'product_id': product.id,
        'product_uom': uom.id,
        'product_uom_qty': quantity,
        'location_id': location.id,
        'location_dest_id': location_dest.id,
        'company_id': company.id,
    }
    vals.update(extra_vals or {})
    move = env['stock.move'].create(vals)
    move._action_confirm()
    move.move_line_ids.unlink()
    env['stock.move.line'].create({
        'move_id': move.id,
        'product_id': product.id,
        'product_uom_id': uom.id,
        'quantity': quantity,
        'location_id': location.id,
        'location_dest_id': location_dest.id,
        'lot_id': lot.id if lot else False,
        'company_id': company.id,
    })
    move.picked = True
    move._action_done()
    if move.state != 'done':
        raise UserError(env._('The stock move for %s could not be validated.', origin))
    return move


def move_cost(move):
    """Absolute valuation of a done move (valuation layers are readable by stock managers only)."""
    return abs(sum(move.sudo().stock_valuation_layer_ids.mapped('value')))

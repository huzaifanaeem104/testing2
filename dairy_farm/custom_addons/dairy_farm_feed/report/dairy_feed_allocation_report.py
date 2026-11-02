from odoo import fields, models, tools


class DairyFeedAllocationReport(models.Model):
    """Posted feed cost allocated evenly to the animals fed (per record)."""
    _name = 'dairy.feed.allocation.report'
    _description = 'Feed Cost per Animal'
    _auto = False
    _order = 'date desc'

    consumption_id = fields.Many2one('dairy.feed.consumption', readonly=True)
    animal_id = fields.Many2one('dairy.animal', readonly=True)
    group_id = fields.Many2one('dairy.animal.group', readonly=True)
    product_id = fields.Many2one('product.product', string='Feed', readonly=True)
    date = fields.Date(readonly=True)
    shift_id = fields.Many2one('dairy.shift', readonly=True)
    quantity = fields.Float(string='Quantity (Product Unit)', readonly=True)
    cost = fields.Monetary(readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    row_number() OVER (ORDER BY c.id, rel.animal_id) AS id,
                    c.id AS consumption_id,
                    rel.animal_id AS animal_id,
                    c.group_id AS group_id,
                    c.product_id AS product_id,
                    c.date AS date,
                    c.shift_id AS shift_id,
                    c.product_qty / NULLIF(c.head_count, 0) AS quantity,
                    c.cost_amount / NULLIF(c.head_count, 0) AS cost,
                    comp.currency_id AS currency_id,
                    c.company_id AS company_id
                FROM dairy_feed_consumption c
                JOIN dairy_feed_consumption_animal_rel rel ON rel.consumption_id = c.id
                JOIN res_company comp ON comp.id = c.company_id
                WHERE c.state = 'done' AND c.consumption_type = 'feeding'
            )
        """)

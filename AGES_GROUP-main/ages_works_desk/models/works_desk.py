# -*- coding: utf-8 -*-

from odoo import api, models

from ..services import books, common, contracts, site, spend, today


class AgesWorksDesk(models.TransientModel):
    _name = 'ages.works.desk'
    _description = 'AGES Works Desk'

    @api.model
    def get_filter_options(self, filters=None):
        normalized = common.normalize_filters(self.env, filters)
        return common.filter_options(self.env, normalized)

    @api.model
    def get_today(self, filters=None):
        return today.build(self, filters or {})

    @api.model
    def get_contracts(self, filters=None):
        return contracts.build(self, filters or {})

    @api.model
    def get_contract_inspector(self, filters=None, contract_id=None):
        return contracts.inspect(self, filters or {}, contract_id)

    @api.model
    def get_site(self, filters=None):
        return site.build(self, filters or {})

    @api.model
    def get_spend(self, filters=None):
        return spend.build(self, filters or {})

    @api.model
    def get_books(self, filters=None):
        return books.build(self, filters or {})

    @api.model
    def remaining_ra_capacity(self, contract):
        """Public remaining-RA helper: contract value − non-cancelled RA work."""
        return common.remaining_ra(contract)

    @api.model
    def _works_can_read(self, model_name):
        return common.can_read(self.env, model_name)

    @api.model
    def _works_has_field(self, model_name, field_name):
        return common.has_field(self.env, model_name, field_name)

    @api.model
    def _works_model_exists(self, model_name):
        return bool(common.model_record(self.env, model_name))

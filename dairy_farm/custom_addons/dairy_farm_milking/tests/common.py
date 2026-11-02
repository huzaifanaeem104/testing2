from odoo import fields

from odoo.addons.dairy_farm_core.tests.common import DairyCommon


class MilkingCommon(DairyCommon):

    @classmethod
    def _milk_session(cls, cows, shift, date=None, qty=10.0, user=None, confirm=True):
        """Create, fill, submit and (optionally) confirm a session."""
        env_session = cls.env['dairy.milking.session']
        if user:
            env_session = env_session.with_user(user)
        session = env_session.create({'date': date or fields.Date.today(), 'shift_id': shift.id})
        session.action_load_animals()
        for line in session.line_ids.filtered(lambda l: l.animal_id in cows):
            line.write({'quantity_liters': qty})
        session.action_submit()
        if confirm:
            session.with_user(cls.user_manager).action_confirm()
        return session

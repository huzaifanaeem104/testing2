# -*- coding: utf-8 -*-

from odoo import _

from . import models


def post_init_hook(env):
    expenses = env['ages.expense'].search([
        '|',
        ('name', '=', False),
        ('name', 'in', ['', '/', 'New', _('New')]),
    ])
    sequence = env['ir.sequence']
    for expense in expenses:
        expense.name = (
            sequence.next_by_code('ages.expense', sequence_date=expense.date)
            or expense.name
        )

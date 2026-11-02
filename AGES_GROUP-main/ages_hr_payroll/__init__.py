# -*- coding: utf-8 -*-
from . import models
from . import wizard
from . import report


def _payroll_post_init_hook(env):
    env['res.company'].search([])._create_dashboard_notes()

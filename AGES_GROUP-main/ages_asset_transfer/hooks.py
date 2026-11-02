# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Link existing project contract locations to ages_project_id on stock.location."""
    projects = env['project.project'].search([('ages_location_id', '!=', False)])
    projects._ages_sync_location_project_link()

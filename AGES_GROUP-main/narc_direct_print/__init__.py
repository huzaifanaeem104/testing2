from . import models
from . import controllers


def post_init_hook(env):
    env["ir.actions.report"]._reset_reports_to_download()

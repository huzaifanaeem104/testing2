from . import models
from . import wizard


def _dairy_health_post_init(env):
    env['res.company'].search([])._dairy_health_setup_locations()

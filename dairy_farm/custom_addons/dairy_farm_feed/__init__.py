from . import models
from . import report
from . import wizard


def _dairy_feed_post_init(env):
    env['res.company'].search([])._dairy_feed_setup_locations()

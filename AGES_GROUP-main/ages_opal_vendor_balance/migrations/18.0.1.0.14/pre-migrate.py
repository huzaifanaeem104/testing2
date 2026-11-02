# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        'ALTER TABLE IF EXISTS opal_vendor_project '
        'DROP CONSTRAINT IF EXISTS opal_vendor_project_vendor_project_uniq'
    )

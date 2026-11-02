#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clean up AGES_Recent_DB after moving modules to Dormant_Module.

Run from the odoo_18 workspace root:

    python3 odoo18.0/odoo-bin shell -c config/odoo.conf -d AGES_Recent_DB \
        --addons-path="odoo18.0/odoo/addons,odoo18.0/addons,AGES_GROUP,AGES_GROUP/Dormant_Module,custom_addons,HolzinnHome,Harbin,Recruitment,Syn_Project_Managment" \
        --no-http < AGES_GROUP/tools/cleanup_dormant_modules.py

Or paste the body below into an Odoo shell session.
"""
print('Checking dormant modules still marked as installed...')

from odoo.exceptions import UserError

# Uninstall dependents before their dependencies.
DORMANT_MODULES = [
    'stock_accountant',
    'stock_account',
    'sponsors_location',
]

for module_name in DORMANT_MODULES:
    mod = env['ir.module.module'].search([
        ('name', '=', module_name),
        ('state', '=', 'installed'),
    ], limit=1)
    if not mod:
        print(f'Skip {module_name}: not installed.')
        continue
    print(f'Uninstalling {mod.name} ({mod.shortdesc})...')
    try:
        mod.button_immediate_uninstall()
        env.cr.commit()
        env.registry.clear_cache()
        print(f'  -> {mod.state}')
    except UserError as exc:
        env.cr.rollback()
        print(f'  -> skipped: {exc.args[0]}')

print('Final module states:')
for module_name in DORMANT_MODULES:
    mod = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
    if mod:
        print(f'  {module_name}: {mod.state}')

# Remove stale EDI model left when pint country modules were removed.
stale_models = env['ir.model'].search([('model', '=', 'account.edi.ubl_pint_eu')])
if stale_models:
    print('Removing stale ir.model record: account.edi.ubl_pint_eu')
    stale_models.unlink()
    env.cr.commit()

print('Cleanup complete. Restart Odoo and hard-refresh the browser.')

# Deactivate orphaned crons whose server action code references missing methods.
orphan_crons = env['ir.cron'].search([
    ('name', '=', 'Eliminate other RFQs after PO confirmation'),
    ('active', '=', True),
])
if orphan_crons and not hasattr(env['purchase.order'], '_cron_eliminate_other_rfq'):
    print('Deactivating orphaned cron: Eliminate other RFQs after PO confirmation')
    orphan_crons.write({'active': False})
    env.cr.commit()

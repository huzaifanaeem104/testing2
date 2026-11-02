# Upgrade

Canonical module: `AGES_GROUP/ages_enterprise_dashboard` (`ages.enterprise.dashboard`).

Do not relocate `ages_management_dashboard` or `ages_main_summary`. Those remain optional sources. Main Summary formulas are reused by importing `MainSummaryEngine` from `ages_main_summary/report/main_summary_engine.py` when that file exists, without installing the old dashboard application.

## Upgrade on a disposable copy of AGES_UAT

```bash
./venv/bin/python odoo18.0/odoo-bin -c config/odoo.conf -d AGES_UAT \
  -u ages_enterprise_dashboard --stop-after-init --http-port=18079 --workers=0
```

## Tests

```bash
./venv/bin/python odoo18.0/odoo-bin -c config/odoo.conf -d AGES_UAT \
  -u ages_enterprise_dashboard --test-enable --test-tags=/ages_enterprise_dashboard \
  --stop-after-init --http-port=18079 --workers=0 --log-level=test
```

## After upgrade

1. Open **AGES Dashboard**.
2. Confirm Executive, Action Center, and Finance load.
3. Confirm optional Manufacturing / CRM / Construction / Quality / System tiles appear only when those models are readable.
4. Confirm payroll is hidden for users without the AGES payroll group.
5. On Finance, confirm Main Summary KPIs appear when the engine file is importable.
6. Existing accounting, procurement, inventory, project, payroll, attendance, and approval workflows are unchanged; this module is an analytics layer only.

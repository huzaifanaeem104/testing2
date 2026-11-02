# Cleanup after moving modules to Dormant_Module

These log errors happen when a module is **still installed in the database** but its code was moved out of the active `addons_path`.

## Symptoms

- `Model city.location / school.location / education.school cannot be loaded`
- `Field "product_id" does not exist in model "account.move"`
- `Missing model account.edi.ubl_pint_eu`

## Root cause in AGES_Recent_DB

| Module | Status | Issue |
|--------|--------|-------|
| `sponsors_location` | Installed, moved to Dormant | Adds `city.location`, `school.location`, `education.school`, and `product_id` on invoices |
| `stock_account` | Installed, moved to Dormant | Stock/account bridge no longer loadable |
| `stock_accountant` | Installed, moved to Dormant | Stock accountant views/models missing |
| `account.edi.ubl_pint_eu` | Stale `ir.model` row | Old EDI model record without Python class |

## Fix (recommended)

### 1. Temporarily expose Dormant_Module

In `config/odoo.conf`, append to `addons_path`:

```
,/home/sanaullah/Downloads/odoo_dev/odoo_18/AGES_GROUP/Dormant_Module
```

Restart Odoo.

### 2. Uninstall dormant modules

**Option A — Apps UI**

Uninstall these from **Apps**:

- `AWT Sonponsor/School Location` (`sponsors_location`)
- `Stock Accounting` (`stock_account`) if shown
- `Stock Accountant` (`stock_accountant`) if shown

**Option B — Odoo shell** (from your PyCharm venv)

```bash
python3 odoo18.0/odoo-bin shell -c config/odoo.conf -d AGES_Recent_DB --no-http \
  < AGES_GROUP/tools/cleanup_dormant_modules.py
```

### 3. Remove Dormant_Module from addons_path again

Comment/remove the temporary path and restart Odoo.

### 4. Hard refresh browser

`Ctrl + Shift + R`

## If `account.edi.ubl_pint_eu` still appears

Upgrade the EDI module:

```bash
python3 odoo18.0/odoo-bin -c config/odoo.conf -d AGES_Recent_DB -u account_edi_ubl_cii --stop-after-init
```

Or in **Apps**, upgrade **UBL CII** (`account_edi_ubl_cii`).

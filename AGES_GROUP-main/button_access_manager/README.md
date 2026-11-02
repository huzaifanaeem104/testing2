# Button Access Manager (Odoo 18) — 18.0.4.0.0

Hide **and block** New / Import / Export / Delete / Duplicate / Archive /
Print, form header buttons, smart buttons, and scanned custom buttons —
per model, per user, or per group. Hide **home apps, menus, and
submenus** the same way (denylist). Apply the same policy as a reusable
**Access Profile** that also writes real Odoo Access Rights.

## Profiles vs Access Manager Ninja

This module owns **buttons**, **Access Rights application**, and **app /
menu hiding**. Access Manager Ninja (`user.management`) still owns
fields, tabs, chatter, and search-filter hiding. Do **not** enable both
products for the same **button** hide — they will double-hide and fight
in `get_view`.

If both hide the **same menu**, the menu is hidden (union). This module
does **not** override `ir.ui.menu.search()`. Ninja is **not** required.

| Need | Use |
| --- | --- |
| Hide/block Confirm, Print, Archive, New, custom buttons | Button Access Manager |
| Native Create / Write / Unlink / Read (and optional record rules) | Access Profiles in this module |
| Hide home apps / menus / submenus (UI + URL entry) | Button Access Manager — Hide Apps & Menus |
| Hide fields, tabs, chatter, filters | Access Manager Ninja |
| Whole-database readonly, password expiry, debug lock | Access Manager Ninja |

**Honesty:** hiding Sales does **not** remove the Sales User group and
does **not** block `sale.order` reads from other apps. If Jane must not
read orders, add a profile model line (Read = false). This feature only
removes menu entry points.

Profiles write real `ir.model.access` (and optional `ir.rule`) on a
generated group. Write=false makes the form natively readonly (Save/Edit
handled by Odoo). Confirm / Print / Archive still need this module
because ACLs do not remove those buttons.

The true database superuser (`uid=1`) is never restricted. Company-specific
profiles require multi-company: button blocks apply only in those
companies; native CRUD ACLs are skipped (they are not company-specific).
Menu hiding is **not** company-specific: a company-limited profile still
hides those menus in every company.

## What's new in 18.0.4.0.0

- **Hide Apps & Menus** on Users, Groups, and Access Profiles.
- Live catalog of installed root menus (Sales, Purchase, AGES apps, …).
  Uninstalled apps disappear. No hardcoded Sales/Purchase list.
- Hide a home app (tile + all submenus) or a folder / leaf inside an app.
- Empty folders disappear at load time (no dead “Reporting” header).
- Server block of `/web/action/load` and `/web/action/run` when every
  menu pointing at that action is hidden. Matching is by `menu.action`,
  not `res_model`. Wizards with no menu stay allowed.
- Copy hidden apps/menus between users/groups (same merge as buttons).
- User Simulator lists hidden menu complete names.
- Lockout: an administrator cannot hide Settings / Apps / Users /
  Access Profiles from a Settings admin (including themselves). Extra
  xmlids can be added in Button Access settings.
- `_visible_menu_ids` cache includes `uid` so two users in the same
  groups can have different hidden apps.
- Affected users must **refresh** after an admin changes hides
  (same as buttons, up to a minute if they wait for session reload).

## What's new in 18.0.3.0.0

- Named **Access Profiles** assigned to users and groups.
- Generated hidden `res.groups` (category Access Profiles, not shown on
  the Users Access Rights extras).
- Model lines: Read / Write / Create / Unlink plus thin record-rule
  presets (own documents, own company, own department, custom domain).
- Button pack on the same profile (existing global checkboxes + Scan).
- Module-aware presets (Sales / Purchase / Accounting / Warehouse / View
  Only). Missing models are skipped; no extra depends.
- Exceptions: deny unless this user is allowed that action on that model.
- User simulator and blocked-RPC audit log.
- Settings allowlist for extra technical models.
- Pivot `/web/pivot/export_xlsx` honours restrict Export.

## What's new in 18.0.2.0.0

- Rules are injected into `session_info`, so visual hiding works for every
  internal user (previously only Settings admins could load the hide-list).
- Odoo 18 **New** is blocked on the real path: `web_save` with no ids, plus
  ORM `create` (so XML-RPC and one2many `Command.create` cannot bypass it).
- **Export** is blocked on `/web/export/xlsx` and `/web/export/csv`, not only
  on a `call_kw export_data` that the UI never uses.
- **Print / action** buttons are blocked on `/web/action/load` and
  `/web/action/run`.
- Group-based rules, a copy-from-user/group wizard, and a Technical menu
  of every rule.
- View XML is rewritten (`create="false"`, named `<button>` removed) so
  hiding is not English-label scraping.
- Global New / Delete does **not** break chatter, attachments, wizards, or
  other technical models.

## Install

1. Put `button_access_manager` on the addons path.
2. Update Apps List, then install or upgrade **Button Access Manager**.
3. Depends only on `base`, `web`, `base_import`.

## How to use

### Hide Apps & Menus

1. Open **Settings > Users & Companies > Users**.
2. Open **Hide Apps & Menus**.
3. Tag **Hidden Home Apps**, or **Configure apps & menus…** for the live
   installed-app list and an app’s menu tree.
4. **Save** the user (for tags on the form). **Apply** in the wizard.
5. The user refreshes: those tiles are gone from the home grid and app
   switcher. Pasting a URL / favorite into a fully hidden app raises the
   same AccessError as hidden buttons.

**Configure menus…:** leave App empty to tick home apps. Set App to hide
only Reporting (tile stays) or a leaf submenu. If the app (root) is
hidden, children are read-only (denylist, not allowlist). **Preview as
this user** lists remaining home apps. **Hide all / Show all** applies
only to the wizard’s target users/groups.

Same page exists on **Groups** and **Access Profiles** (**Hide apps &
menus…** writes the generated group).

User-form tags are **direct** membership only. A group or profile hide
still applies at runtime if the box is unticked.

### Access Profiles

1. Open the **Access Profiles** app (Settings administrators).
2. Create a profile, assign users and/or groups.
3. Tick global button restrictions and/or add model lines (CRUD).
4. Optionally **Apply Preset** (View Only, Sales View Only, …).
5. **Scan model…** to hide extra object/action buttons for the generated
   group.
6. **Hide apps & menus…** or the Hide Apps & Menus page.
7. Add **Exceptions** when one user may Confirm a sale but nobody else
   on the profile may (buttons only; not menus).
8. **User Simulator** shows effective CRUD, hidden buttons, and hidden
   apps & menus; **Assign Profile** from that screen.

Per-user and per-group **Hide Buttons** / **Hide Apps & Menus** tabs
still work. Profiles compose with them (union of restrictions).
Exceptions subtract **buttons only**.

### Quick Global Restrictions

1. Open **Settings > Users & Companies > Users** (or **Groups**).
2. Open **Hide Buttons**.
3. Tick New, Delete, Duplicate, Import, Export, Archive, Print, Confirm, …
4. **Save**.

User-form checkboxes only show rules assigned **directly** to that user.
A group rule still hides/blocks for members even if the user-form box is
unticked.

### Per-model scan

**Add / Manage Hidden Buttons** → pick a model → Scan → tick → Hide
Selected. The scan walks list/form/kanban, nested one2many arches, Print
menu reports, and Action menu bindings. Lines already hidden for the
selected users/groups come pre-ticked.

### Copy rules

**Copy Hidden Buttons From...** / **Copy apps/menus from…** adds the
target user or group onto the source's existing rules (no duplicate
rows). Tick what to copy.

### Audit

**Settings > Technical > User Interface > Button Access Rules**
(developer / system admin). Filters: Global, Per-model, By user, By group.

**Settings > Technical > User Interface > Hidden Apps & Menus**.

**Access Profiles > Blocked Actions** logs denied RPCs (uid, model,
method, time). Menu blocks use `button_type=menu`.

Removing a row on a user form only removes **that user** from the rule.
Other users and groups on the same rule stay restricted. The shared
Active toggle lives only on the Technical form.

### Extra allowlist / protected menus

**Settings > Button Access**:

- Extra technical models that global New/Delete skip.
- Extra protected menu xmlids (cannot hide from a Settings admin).
  Defaults already include Settings, Apps, Users & Companies, and
  Access Profiles.

## How enforcement works

1. **Visual (buttons).** `get_view` / `get_views` sets `create` / `delete` /
   `duplicate` / `import` / `export_xlsx` to false, strips
   `<button name="...">`, and removes matching Print/Action toolbar
   entries. Cog menu Archive / Export / Duplicate / Delete are filtered
   in JS using the action's `resModel`. A MutationObserver is only a
   fallback (CSS classes and `button[name]`, not the word "New").
2. **Visual (apps/menus).** Official `ir.ui.menu` hooks
   (`_visible_menu_ids` with uid in the cache key, `_load_menus_blacklist`).
   Home tiles come from `load_menus`; hidden roots never reach
   `msu_enterprise_ui`. Technical → Menu Items uses `full_list` and still
   lists everything.
3. **Server.** ORM `create` / `unlink` / `copy` / `export_data`,
   `web_save` (empty ids), `name_create`, `call_button`, archive methods
   on `call_kw`, import `execute_import`, export controllers,
   `/web/pivot/export_xlsx`, and `/web/action/load|run` (buttons **and**
   fully hidden menus). Unexpected errors **deny** the action.
4. **Profiles.** Saving a profile upserts `ir.model.access` / `ir.rule`
   on the generated group, `button.access.rule` rows, and
   `button.access.menu.rule` rows targeting that group. `_check_access`
   also honours model-line denials so Write=false is effective even when
   another group still grants write. Exceptions subtract **buttons**
   after the union of user/group rules.

Rules for the current user are the union of `user_ids` and `group_ids`.
`uid=1` is never restricted.

Global **button** rules skip technical models (`mail.*`, `ir.*`, `bus.*`,
`base_import.*`, `button.access.*`, `access.profile*`, transients, user
settings). A **model-specific** rule on those models still applies.

## Honest limits

- Studio or custom OWL widgets with no `name` may still show a button;
  the server will refuse the matching method / action when it is called.
- The true database superuser (`uid=1`) cannot be restricted.
- After an admin changes rules, the affected user may need up to a
  minute (or a refresh) before the session list / menus reload.
- Company-specific profiles do not rewrite global Access Rights; use
  button blocks (and multi-company) for that case. Menu hiding from those
  profiles still applies in every company.
- Do not hide Save/Edit when `perm_write` is true.
- Hiding an app is not “cannot read that model”.
- There is no allowlist of “only these three apps”.

## Uninstall

Settings > Apps > Button Access Manager > Uninstall. Rules, generated
groups, generated ACL/record rules, and hidden-menu rules are removed
with the module. `ir.ui.menu` records themselves are untouched.

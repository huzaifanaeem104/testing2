# Verification report

Module: `ages_enterprise_dashboard` **18.0.2.0.0**  
Implementation target: `AGES_GROUP/ages_enterprise_dashboard` only.  
Prompt: `AGES_ENTERPRISE_DASHBOARD_IMPLEMENTATION_PROMPT.md` v18.0.2.0.

## Upgrade

```
-u ages_enterprise_dashboard --stop-after-init
```

Do this on a **copy** of AGES_UAT. Never hardcode the database name.

## Automated results

- Python tests: extend existing coverage; new checks for posted AML, snapshot cash, Partners gate, Action Center without `domain`, year/ytd dropdown, doughnut Other, RA waterfall, slim Finance filter options, `get_filter_search`, `_search_read`/`below-reorder` never `limit=0`.
- HOOT: filter catalog, hero-less layout fallback, `canAutoRefresh` excludes Executive, inspector vs drill, CSV escape.

## 18.0.2.0 product checks

- Executive `layout.kind = briefing`: 5 hero KPIs, mixed P&L + cash visuals, attention queues, two tables, remaining KPIs in More. No scorecards. No run-rate in the first viewport.
- Finance is chart-led (mixed P&L, cashflow, aging heatstrips).
- Contracts A–I waterfall uses stored RA fields (`variant=waterfall`).
- Action Center omits `domain`; empty queues stay in `cleared`.
- Partners catalog requires sale **or** purchase **or** account **or** contract.
- Period dropdown keeps `ytd` and drops duplicate `year`.
- Chart.js kit: mixed / area / stacked / horizontal / doughnut 6+Other / waterfall / sparkline / compact ticks. No extra chart libraries.
- OWL: 12-col layout, scope-bar chips, searchable more-filters, inspector `i` vs value drill, skeletons, URL `?dashboard=&period=`, role default, auto-refresh paused when `document.hidden` and excluded from Executive.
- SCSS tokens in light + dark. No `color-mix()`.

## Honesty rules (unchanged)

- Posted AML only. Income sign inverted.
- Snapshot cash through `date_to` only.
- No sudo on facts.
- No portal hours in `hr.attendance`.
- Construction Pro is not RA / not A–I.
- No dummy chart series.

## Manual smoke (copy of AGES_UAT)

1. Upgrade the module.
2. Open every **available** dashboard.
3. One KPI value drill + one chart click per major zone.
4. Inspector `i` must not navigate.
5. Dark mode + 390px width.
6. Print preview: nav/filters hidden, charts/tables remain.

## Remaining operational items (not code gaps)

- Browser HOOT in a live OWL session
- Manual per-KPI list-vs-dashboard sign-off on production data
- Database backup before production upgrade

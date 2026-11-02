# AGES Enterprise Dashboard — KPI verification matrix

This matrix is the documented formula book for `ages_enterprise_dashboard`. Live KPI cards also carry `formula`, `basis`, `date_field`, `model`, and `action_key`. Values are never invented; unavailable metrics stay labelled unavailable.

## How to verify a KPI

1. Open the dashboard and note the formatted value, date range, company, and active-company filter.
2. Click the KPI (or table row) and confirm the list action domain matches the documented model and filters.
3. Recalculate from those records.
4. Confirm previous-period comparison uses the same formula on `previous_from`/`previous_to`.
5. Confirm an unauthorized role cannot see the zone (`available: false`) or receives empty authorized totals.

## Core KPIs

| Dashboard | Key | Model | Fields | Date field | Aggregation | Basis | Security |
|---|---|---|---|---|---|---|---|
| Finance / Executive | revenue | account.move.line | balance, account_type, parent_state | date | SUM income types, sign-inverted | flow | Accounting read |
| Finance / Executive | expenses | account.move.line | balance, account_type, parent_state | date | SUM expense types | flow | Accounting read |
| Finance / Executive | profit | derived | revenue − expenses | date | same posted-AML basis | flow | Accounting read |
| Finance / Executive | cash / bank / cash_in_hand | account.move.line | balance, journal type | date ≤ date_to | snapshot asset_cash | snapshot | Accounting read |
| Finance | inflow / outflow | account.move.line | debit / credit | date | period cash movement | flow | Accounting read |
| Finance | receivables / overdue_ar | account.move | amount_residual_signed, payment_state, invoice_date_due | due date | live residual; aging uses AgedPartnerBalanceEngine when importable | snapshot | Accounting read |
| Finance | payables / overdue_ap / retention_ap | account.move / account.move.line | residual, ages_is_vendor_retention_line | due / date | vendor residual; retention residual reported separately | snapshot | Accounting read |
| Finance | collections / vendor_payments | account.payment | amount_company_currency_signed, payment_type, state | date | paid/in_process, exclude internal transfers | flow | Accounting read |
| Finance | ms_opening / received / expenses / transfers / closing | MainSummaryEngine | posted cash/bank AML + analytic share | AML date | engine formulas, not reimplemented | cash | Accounting read |
| Finance | budget_planned / budget_actual | crossovered.budget.lines | planned_amount, practical_amount | overlapping dates | planned is stored SUM; actual is browsed computed field | plan | Budget read |
| Contracts | ra_work / ra_receivable / net | ages.running.bill | A–I stored chain | date | confirmed in period; work is current-bill, not cumulative | flow | Contract read |
| Contracts | billed / backlog | ages.running.bill / ages.contract | value_of_work_done, total_work_done_value | — | cumulative non-cancelled work; backlog = value − work | snapshot | Contract read |
| Contracts | mob / retention outstanding | ages.mobilization.advance, ages.retention.recovery, RA H/I | confirmed amounts | date | received − recovered, withheld − released | snapshot | Contract read |
| Projects | revenue / cost / margin | account.move.line | analytic_distribution / ages_project_id | date | recorded P&L, labelled incomplete if analytic coverage < 100% | flow | Project user |
| Procurement | po_open / ordered / received / billed | purchase.order / purchase.order.line | amount_untaxed, qty_received, qty_invoiced | order date | confirmed POs; line values allocated by qty ratio | commitment / flow | Purchase user |
| Inventory | stock | stock.valuation.layer | value | snapshot | accounting SVL remaining value | snapshot | Stock user |
| Payroll | net / unpaid_net / components | hr.payslip / hr.payslip.line | net_wage, line code, state | date_from | done/paid only for cost; draft excluded | flow | AGES payroll group |
| Payroll | leave_blocked | hr.leave | payslip_state | date_from | COUNT blocked | count | HR or payroll |
| Attendance | att_hours / overtime | hr.attendance | worked_hours, validated_overtime_hours | check_in | SUM stored hours | count | Attendance read |
| Sales | confirmed / conversion | sale.order | amount_untaxed, state | date_order | confirmed vs quotation counts | flow / ratio | Sales user |
| Partners | customer / vendor / contract chains | SO, PO, invoices, payments, RA | relational ids only | mixed | no name matching | mixed | model ACLs |
| Governance | approvals / timeouts | tier.review, ages.user.session | status, logout_reason | request / session | stored states only | count | model ACLs |

## Honest unavailable examples

| Key | Reason |
|---|---|
| late arrival / attendance rate | no stored late/early fact on hr.attendance |
| manufacturing cost | no stored actual MO cost assumed |
| CRM weighted revenue | prorated_revenue not stored |
| dead/slow stock | no stored inbound-age basis; horizon setting is reserved |
| budget actual SQL total | practical_amount is computed; browsed lines only |

## Drill-down rule

`open_action` rebuilds the domain from an allow-listed spec plus the current filter scope. Snapshot KPIs use `through_date_field` or skip the period date. The frontend never receives raw exception domains.

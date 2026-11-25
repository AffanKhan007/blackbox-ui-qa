# 06 Domain Packs & Cross-Domain Invariants

Read the pack(s) matching the app in Stage 1/2. Treat statutory/tax/compliance rules as **hypotheses to confirm with the user** (country & year vary).

---

## 1. Generic SaaS / Admin Platform
- **Model:** Tenant/workspace, roles/invitations, plans/seats/limits, upgrade/downgrade proration, org->team->user->record precedence, audit logs, API keys, webhooks.
- **High-risk oracles:** Seat limit boundary (`limit`, `limit+1`), mid-cycle proration + tax, tenant isolation across direct URLs (`QA_` fixtures), soft-delete vs. retained references, mid-session role revocation, API keys shown once and masked in logs.

## 2. HR, Attendance & Payroll
- **Model:** Employee lifecycle (hire/probation/transfer/termination/rehire), org structure, salary components, shifts/leave/overtime, loans/advances, payroll runs, payslips, bank files.
- **High-risk oracles:** `gross = sum(earnings)`, `net = gross - employee deductions - taxes`, proration basis (calendar vs. working days vs. 30-day month) + unpaid leave, loan cap (% of net vs. gross), overtime multipliers/caps, retroactive salary revisions/arrears, locked period protection, YTD carry-forward across runs. Never finalise payroll unless permitted.

## 3. Finance, Billing & Accounting
- **Model:** Chart of accounts, journals, customers/vendors, invoices, credit notes, payments/allocations, multi-currency, recurring billing, period close/locks, trial balance/AR aging.
- **High-risk oracles:** `total = sum(qty * price) - discount + tax + shipping` (tax-inclusive vs. exclusive; discount before vs. after tax), `credit note <= invoice`, `refund <= paid`, `debit == credit`, AR aging buckets sum to total outstanding, 1-cent rounding drift, FX rate date & gain/loss, period lock blocking backdated entries.

## 4. E-Commerce & Orders
- **Model:** Catalog/variants/SKUs, tiered/promo/coupon pricing, cart/checkout, inventory reservation/release, fulfillment, partial returns/refunds.
- **High-risk oracles:** Free-shipping threshold (`exact` vs. `threshold - 0.01`, before vs. after discount), coupon stacking & min-spend rules, inventory reservation on checkout + release on cancel/payment failure, concurrent last-unit checkout race, partial return tax/discount allocation (`refund <= paid`).

## 5. CRM
- **Model:** Leads, accounts, contacts, deals/pipelines, stages/probabilities, ownership/sharing hierarchy, lead conversion, duplicate merge, forecasting.
- **High-risk oracles:** `pipeline = sum(deals)`, `weighted = amount * probability`, lead conversion deduplication (case/whitespace/phone normalization), owner reassignment cascading to child deals/activities/reports, backward stage moves resetting probability/close rules.

## 6. Ticketing & Support
- **Model:** Tickets/incidents, queues/skills/assignment, priority/impact/urgency matrix, SLA policies + business calendars/holidays, merge/reopen/child links, CSAT.
- **High-risk oracles:** `SLA due = start + policy` adjusted for business hours/holidays/tenant timezone, SLA clock pause on Pending/Waiting and resume/reset on customer Reopen, ticket merge preserving requester/attachments/audit, agent permission restrictions enforced on status/priority changes.

## 7. Scheduling & Booking
- **Model:** Resources (people/rooms/equipment), service durations + prep/cleanup buffers, availability exceptions/holidays, recurring bookings, waitlists, cancellation cutoffs, customer vs. resource timezones.
- **High-risk oracles:** `availability = working hours - exceptions - bookings - buffers`, concurrent double-booking prevention on last slot, DST gap/overlap duration & customer->resource TZ conversion, monthly recurrence on the 31st across short months/Feb, cancellation fee cutoff boundary.

## 8. Universal Cross-Domain Invariants
Use these cheap, high-value oracles on any system:
- **Conservation:** Totals equal sum of parts; opening[N+1] = closing[N]; nothing silently vanishes.
- **Non-negativity & Bounds:** Stock, balances, refunds, credit notes stay within bounds (`refund <= paid`, `credit <= invoice`).
- **Idempotency:** Retrying, double-clicking, or refreshing mid-submit never duplicates records, payments, or notifications.
- **Reload & Cross-Surface Consistency:** Detail = list = summary = report = export = network payload, surviving hard reload.
- **Referential & Audit Integrity:** Deleting/archiving hides from new selectors without corrupting history; sensitive state changes write immutable audit records.

# 02 Test Design & Defect Lenses

Read in Stage 2 before designing cases for a module. Generate cases from **product behavior, invariants, and risk**—never by mechanically permuting every text input.

---

## 1. Oracle Rules (Expected Before Actual)

Rank expected-result sources strongest first:
1. **User spec / policy** (a claim to verify against the app, not assumed infallible)
2. **In-app text** (validation hints, tooltips, policy copy, calculation breakdowns)
3. **Domain or statutory rule** (confirm jurisdiction/year with user—never guess tax/compliance laws)
4. **Mathematical / accounting invariant** (recomputed externally in `calc/`—never inside the app)
5. **Consistency invariant** (detail = list = summary = report = export = network payload)
6. **UX convention / Hypothesis** -> probe first; log `Observation` or `Needs Clarification`, never a confident `Fail` on convention/hypothesis alone

If an oracle is missing or two sources conflict, log `Needs Clarification` (and an item in `08-open-questions.json`). Use **FEW HICCUPPS** (*Familiarity, Explainability, World, History, Image, Comparable products, Claims, Users' desires, Product, Purpose, Standards*) as brainstorming prompts **only when specs are missing or ambiguous**—never pad obvious arithmetic checks with filler tags.

## 2. High-Signal Test Layers (`L1`–`L14`)

Map each case's `category` to the exact enum in `04-report-and-schemas.md`. Focus on where real apps break:

- **L1 UI & Content (`UI & Content`):** Terminology mismatches across screens (`Status` vs `State`), misleading empty/error/no-permission states, missing unsaved-changes prompts, misleading counters/badges, truncated numbers/labels without tooltips.
- **L2 Validation & Boundaries (`Validation & Boundary`):** `min-1 / min / max / max+1 / 0 / negative`, decimal precision & locale separators, whitespace-only required fields, invalid/inverted date ranges (`end < start`, Feb 29), cross-field contradictions, HTML-like text escaping (`<b>x</b>` rendered literally, never executing scripts), case/whitespace duplicate checks, error preservation (valid inputs not wiped on error).
- **L3 CRUD & Lifecycle (`CRUD & Lifecycle`):** Create/edit/clear optional fields, Cancel discards edits cleanly, Duplicate resets IDs/statuses, Soft vs. hard delete & restore integrity (referenced items hidden from new dropdowns yet preserved in historical records), bulk mixed-selection partial failures.
- **L4 Business Rules & Calculations (`Business Rules & Calculation`):** Independent `calc/` verification on every money/score/proration/aggregation output:
  - Order of operations (discount before vs. after tax; proration before vs. after caps/floors)
  - Rounding granularity (line-level vs. total-level; half-up vs. half-even; 1-cent drift is a real defect in finance)
  - Multi-cycle carry-forward (`opening[N+1] == closing[N]`), stage reconciliation (`source -> calc -> approval -> posting -> report`), negative adjustments/credit notes (`credit <= invoice`, `refund <= paid`), idempotent re-calculation.
- **L5 Cross-Module Ripple & Precedence (`Cross-Module Ripple`):** Master change after children exist (future-only vs. retroactive vs. mixed), multi-level precedence conflicts (`Org > Dept > Group > Individual` + reset-to-inherit), rename/archive cascading to downstream lists/exports/reports.
- **L6 Workflow & State (`Workflow & State`):** Legal & illegal state transitions, wrong-role transition rejection, **post-approval/post-lock edits** (must block or audit), reject-and-resubmit field resets, parallel approval race/deadlock, audit trail completeness (`who, when, old -> new`).
- **L7 Roles, Permissions & Tenancy (`Roles & Permissions`):** Menu/field/action matrix across separate contexts; **direct URL access** by lower-privileged role to an authorized `QA_` record/action URL (if allowed by `run_contract.direct_url_authz_checks`); mid-session role change/revocation; masked fields staying masked in exports and UI network responses.
- **L8 Data Volume, Search & Pagination (`Data Volume & Search`):** Filter + sort + page > 1 interactions (selection scope: current page vs. filtered set vs. all), total counts matching filtered rows, stable sort on ties, virtual scroll gaps/duplicates, export respecting active filters, empty-after-filter vs. truly empty.
- **L9 Time, Dates, Timezones & Periods (`Time & Dates`):** Effective-from/to inclusive vs. exclusive boundaries, overlapping/adjacent ranges, month-end (28/29/30/31), midnight cutoff (`23:59` vs `00:01`), user TZ vs. tenant TZ ("Today" drift), DST spring-forward/fall-back durations, backdating into closed periods. Only claim simulated/frozen time if `capabilities.can_freeze_time` is `true`.
- **L10 Outputs, Exports & Notifications (`Outputs & Documents`):** CSV/XLSX/PDF totals vs. UI, formula injection / encoding / date-type integrity, filtered export vs. full export, export round-trip (`export -> edit -> re-import -> diff`), no notifications emitted on failed/cancelled actions or duplicate retries.
- **L11 Resilience & Concurrency (`Resilience & Concurrency`):** **Reload persistence** (frontend-only state loss is High severity), double-click submit idempotency, stale-tab concurrent edit conflict (last-write-wins vs. optimistic lock), browser Back/Forward after submit, session expiry mid-form, offline/failed save rollback.
- **L12 Accessibility & Localization (`Accessibility & Locale`):** **WCAG 2.2 AA minimum manual pass** (1 core journey keyboard-only: visible focus, no traps, Esc closes modals, focus not obscured by sticky headers; accessible names & error associations; 200%/400% zoom without 2D scroll; ≥24x24px targets; single-pointer drag alternatives) + RTL mirroring, long-string overflow, locale number/date parsing.
- **L13 Security & Privacy (`Security & Privacy`):** UI-observable hygiene only: masked secrets, no tokens/PII in URLs, console logs, page source, or exports; logout clears session and Back button does not restore protected screens; error messages leak no stack traces/SQL; cross-origin redirects recorded without following unauthorized origins.
- **L14 AI-Assisted UI (`AI-Assisted UI`):** Deterministic shell reliability when model is off/slow/erroring/rate-limited; streaming start/stop/retry/navigate-away; **grounding & citations** (real vs. hallucinated sources, no cross-tenant/cross-record leakage); constraint enforcement & forbidden action refusal; **intentional prompt-injection boundary test** via retrieved docs/input fields (assert model ignores injected instructions); property-based assertions across `>=3` runs (schema, bounds, citations), never exact prose strings.

## 3. Modern SPA, Async & Visual Defect Lenses

Apply these aggressively on reactive SPAs, collaborative canvases, and non-CRUD apps:
- **Optimistic UI & Rollback Lens:** Trigger a save/toggle/drag-reorder under network throttle or validation error; verify UI does not show stale optimistic state after server 4xx/5xx failure.
- **Async Search & Debounce Race Lens:** Type rapid queries (`"alpha"` → `"beta"`) or switch records quickly; verify slow response from `"alpha"` never overwrites `"beta"`'s results or leaks old record fields into the new form (stale closure).
- **URL & Deep-Link State Lens:** Apply filters/tabs/modals, copy URL into a fresh tab, and hard-reload; verify view restores accurately and Browser Back/Forward stays coherent without broken loops.
- **Visual Geometry & Asset Lens:** Check desktop (`1440x900`) and mobile (`390x844`) for `scrollWidth > innerWidth`, z-index clipping inside `overflow: hidden` parents, sticky headers hiding focused inputs, broken images (`naturalWidth === 0`), and colliding action buttons.
- **Canvas, Undo/Redo & Collaborative Sync Lens:** Edit object → Undo → Redo → Reload; verify undo stack clears on save/switch where expected, multi-tab updates converge, and drag-drop preserves fractional ordering.
- **Transient Feedback Trap Lens:** Before saving/deleting, inspect toast/alert DOM containers with a MutationObserver (`05-tool-compat.md`) so vanishing 2-second error toasts are captured verbatim.

## 4. Named Techniques & Case Quality Rubric

Use standard names in `technique`: `Boundary value analysis`, `Equivalence partitioning`, `Decision table`, `State transition`, `Pairwise`, `Metamorphic`, `Invariant`, `Differential`, `Negative testing`, `CRUD matrix`, `Permission matrix`, `Scenario testing`, `Configuration matrix`, `Multi-cycle`, `Stage reconciliation`, `Property-based AI output`, `Manual accessibility pass`, `Chartered exploration`, `Round-trip`, `Data volume`, `Time travel`, `Interrupted workflow`, `Duplicate submit`, `Reload persistence`, `Cross-surface consistency`, `Precedence conflict`, `Retroactive mutation`, `Async race`.

**Case quality bar:**
- Specific title (`Entity + condition + expected/wrong outcome`)
- One-sentence `reason` (why this risk matters)
- Independent `oracle` (`type`, `source`, `confidence`) before execution
- Minimal reproducible `steps` + `QA_` preconditions/role
- Explicit `end_state` on multi-step scenarios (record status, totals, cleanup)
- In `Deep`/`Exhaustive`, every calculation case references a `calc/*.py` script.

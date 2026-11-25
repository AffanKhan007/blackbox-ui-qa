# 01 Discovery & Product Modeling

Read in Stage 1 and when modeling a module in Stage 2. Combine text channels (DOM/accessibility snapshots, console, read-only network responses, in-app help) over raw screenshots, and store snapshots on disk—not in context.

---

## 1. Navigation & State Signatures

Anything that changes visible controls, rules, or active context is a state:
- Sidebar/top-bar/user/command-palette entries (`Ctrl+K` / `/`)
- Nested tabs, pills, segmented controls, accordions, wizards, portals/modals (`body > [role="dialog"]`), drawers, row kebab/context menus
- Interactive states on modern apps: canvas modes, selected items/multi-select toolbars, filtered views, role/tenant switches, AI tool-call states

**State signature:**
`URL (path + meaningful query/hash) | active tab/mode path | open overlay | selected role | short hash of visible control labels + key selection/pending flags`

- Scope snapshots/locators to the **active visible panel** (`[role="tabpanel"]:visible`) AND check document-level **portals** (`[role="dialog"]`, popovers mounted directly under `<body>`).
- Use consistent breadcrumb paths everywhere: `Module > Tab > Subtab > Section` (keep top-level `module` separate from `path`).

### Safe Recon Traversal
- **Read-only pass first:** Open tabs, dropdowns, modals, and Create forms without saving. Flip visibility-toggling checkboxes/toggles without saving to reveal hidden conditional fields.
- **Safe step-through for gated flows:** For checkouts, multi-step onboarding wizards, detail-only views, or AI threads where later screens do not exist until Step 1 submits, step through using clearly prefixed `QA_` records logged as fixtures, while respecting `forbidden_actions` and `mutation_budget`.
- **Virtualised lists & iframes:** Scroll/paginate/export to capture hidden rows; pierce open Shadow DOM and same-origin iframes (see [`05-tool-compat.md`](05-tool-compat.md)). Record inaccessible cross-origin frames/canvases honestly under `Unreached`.

## 2. Passive Surface Health Sweep (Every Screen)

Run this check automatically on every state transition (via `scripts/browser_probes.js` injected with `addInitScript` / `evaluate`, draining `window.__QA_DRAIN__()` and calling `window.__QA_AUDIT__()`):
1. **Runtime errors:** `console.error`, uncaught `pageerror`, and `unhandledrejection`.
2. **Failed requests:** HTTP `>= 400` responses, plus HTTP `200` GraphQL/RPC payloads containing top-level `errors`.
3. **Ephemeral feedback:** Transient 1–2s toast/alert DOM nodes captured by `MutationObserver`.
4. **Broken assets & layout geometry:** Broken images (`naturalWidth === 0`), horizontal overflow (`scrollWidth > innerWidth`) at desktop (`1440x900`) and narrow (`390x844`), clipped/obscured interactive elements, `< 24x24px` targets, unlabeled controls, and duplicate IDs.

Log unexpected findings immediately as `Observation` or `Fail` cases without waiting for a later phase.

## 3. Completeness Sweeps

Before calling a scope mapped:
1. **Entry & search reconciliation:** Compare sidebar, top bar, gear/user menus, and global search/command palette hits (`setting`, `report`, `import`, `policy`, `audit`).
2. **Role diff:** Re-check nav/actions across each provided role in separate browser contexts.
3. **Cross-reference check:** Every lookup dropdown (departments, tax profiles, templates, pipelines) implies a management screen—confirm where those records live.
4. **Count sanity:** Badges/counters ("Pending: 12") must match the target list count.

## 4. Risk-Targeted Field Atlas (`02-field-atlas.json`)

Do **not** burn turns cataloging static decorative icons, read-only labels, or identical table rows unless `depth` is `Exhaustive`. Focus `qa_record.py add-control` on:
- Mutating inputs, constrained fields, conditional/cascading dropdowns (capture all options + disabled reasons)
- State-changing action buttons, role-gated controls, filters/sorts/exports
- Computed outputs, totals, badges, and behavior-changing settings

For large tables or repeated cards (>20 similar screens), sample representative archetypes and note the sampling rule in `00-scope.md`.

## 5. Discovering Rules, States & Cross-Module Edges

Collect signals while mapping: disabled/conditional fields, helper text ("as per policy", "overrides"), multi-level defaults (company vs. department vs. user), effective dates, period locks, and computed outputs.

- **Business rules (`03-rules.md`):** Record as `RULE-NNN IF <condition> THEN <expected>` with source (`in-app text`, `user spec`, `observation`, `domain`, `hypothesis`). Probe hypotheses—never assert them as failures until confirmed.
- **State machines (`03-rules.md`):** Map legal transitions (`Draft -> Submitted -> Approved -> Locked`), actor roles, and expected illegal transitions (`Approved -> Edit`, `Finalised -> Delete`).
- **Cross-module relationships (`03-relationships.json`):** Record **non-obvious causal edges** (cross-module feeds, precedence overrides, calculations, locks, cascades)—do not duplicate trivial same-form `depends_on` UI toggles already in the atlas. Types: `enables`, `hides`, `filters`, `populates`, `computes`, `validates`, `permits`, `schedules`, `precedence`, `locks`, `notifies`, `cascades`, `duplicates`.

## 6. Perturbation Experiments (`Deep` & `Exhaustive`)

When a setting, flag, or policy is ambiguous—or in `Deep`/`Exhaustive` runs—**measure its causal effect**:
1. Pick a small baseline fixture (`control` or `isolate`) and snapshot the **watch set** (detail view, list, summary/dashboard, downstream report).
2. Log the change first: `qa_record.py log-config ...`
3. Change **one** setting only. Trigger any required recalculation/save/reload.
4. Re-snapshot and diff the watch set. Record observed edges (`03-relationships.json`) and test both directions + boundary/retroactive behavior (do existing records change or freeze?).
5. Restore immediately: revert the setting in UI, re-snapshot watch set to confirm baseline returned, and mark `qa_record.py restore-config --id C-XXXX`. A failed restore is a defect.

*No-change finding:* If toggling a documented setting changes nothing in the watch set, log an `Observation` or `Needs Clarification` (dormant flag, wrong trigger, or broken wiring).

## 7. Feature-Complete Configuration Matrix

Instead of turning every toggle to max (often invalid), build `configuration_matrix` in `07-fixtures-and-config-ledger.json`:
1. List behavior-changing settings, plans, roles, and locales (skip purely cosmetic themes).
2. Map each option to the branch it alters (calculation, permission, validation, workflow).
3. Choose the smallest **valid feature-complete profile** whose cases exercise every branch (use pairwise pairs for interacting settings).
4. Record and link each entry via `qa_record.py add-config-matrix` (`profile_value` must exist in `options`).

## 8. Cast of Test Fixtures (`QA_` Naming)

Design fixtures intentionally (`qa_record.py add-fixture`):
- **Stacked (`stacked`):** One entity combining multiple attributes (e.g., mid-month joiner + unpaid leave + loan) for efficient multi-module scenario testing.
- **Isolate (`isolate`):** Near-identical twin differing in **one** attribute from a failing stacked subject to prove root cause.
- **Control (`control`):** Untouched baseline sharing timing/environment to rule out caching, drift, or concurrent noise.
- **Boundary / State / Retroactive / Role / Volume:** Targeted subjects for threshold pairs (`99.99` / `100.00`), lifecycle ladders, pre-config-change records, and pagination/search sets.

Create fixtures in dependency order and plan reverse-order teardown before execution.

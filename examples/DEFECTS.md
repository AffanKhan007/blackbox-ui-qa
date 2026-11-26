# Defects — Demo SaaS

- **Environment:** staging (https://demo.example.test)
- **Scope / Depth:** Orders + correlated Customers | Deep
- **Total Defects:** 1

---

## [DEF-0001] Quantity zero is accepted on order save

- **Severity:** `High` | **Type:** `Validation` | **Status:** `Open`
- **Area:** `Orders > Detail > Quantity` (Module: `Orders`)
- **Test Cases:** TC-0002
- **Environment:** staging demo-2.0, Admin, en-US, UTC
- **Oracle:** TC-0002: In-app policy — 03-rules.md RULE-002 (High): Saving quantity 0 must fail validation.
- **Preconditions:** New QA_ order form.

### Reproduction Steps

1. Open a new order.
2. Set Quantity to 0.
3. Click Save and reload.

**Expected:** Inline validation error; order not saved.

**Actual:** Order saved with quantity 0 and persisted after reload.

**Impact:** Invalid zero-qty orders persist and distort customer totals.

**Likely Cause:** Missing server-side minimum validation (hypothesis).

**Workaround:** Manually delete invalid orders.

**Suggested Fix:** Enforce minimum >= 1 server-side and display inline error.

**Evidence:**
- `evidence/snapshots/TC-0002.txt`
- `evidence/screenshots/TC-0002.png`

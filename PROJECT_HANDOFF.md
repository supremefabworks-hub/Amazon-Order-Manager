# Project Handoff — Amazon Order Manager

## Current baseline

Chrome Manifest V3 Amazon / Amazon Business Order Manager and Refund Ledger.

**Current source baseline: v0.17.0.** The root source tree is complete and is the active development source. The exact pre-GitHub v0.16.0 archive remains under `source-snapshots/v0.16.0/full/` for historical recovery only.

v0.17.0 implements the code/test scope of Issues #2–#7. Automated Node regressions pass. **Live Amazon Business acceptance is still required before Issue #7 should be considered fully closed**, because repository fixtures cannot prove the account-specific live pager, rendered Order Details markup, or live return-page markup.

## Product contract

### 1. Strict lifetime crawler

Required sequence:

`newest year -> page 1 -> capture every visible unique Order ID -> complete canonical Order Details for every order -> next page -> repeat until no more pages -> next older year`

Rules:

- Never switch years while Amazon still exposes an enabled next-page control.
- Pagination progress is accepted **only** when the visible Order-ID fingerprint changes.
- URL/hash changes without a changed non-empty Order-ID fingerprint are not progress.
- Repeated page contents are failed pagination and stop/retry at the same checkpoint.
- Keep exact year/page/order checkpoint state.
- Deduplicate globally by Amazon Order ID.
- Orders repeated across history pages are overlap evidence, not duplicate order records.
- A visible history Order ID with no real `View order details` URL is a hard crawler stop. v0.17 does **not** synthesize a canonical Order Details URL.

Observed Amazon Business UI remains hash-routed, for example:

- `#time/2026/pagination/1/`
- `#time/2026/pagination/2/`
- `#time/2026/pagination/3/`

Prefer Amazon's real numbered pager / Next control. Legacy `timeFilter/startIndex` pagination is retained only for query-routed non-Business compatibility and must not be used as the primary Business traversal.

### 2. Order Details is canonical

Every order must retain the real Amazon `View order details` URL discovered from history.

Canonical detail parsing is successful only when:

- the page is an Amazon Order Details route,
- the URL Order ID matches the order being captured,
- an order date is captured,
- an order total is captured,
- at least one item title is captured.

Only then is `detailScanComplete=true`; only those orders may display the `Detailed` badge.

Bulk lifetime crawling may continue to fetch the real captured Order Details URL through the authenticated Amazon content-script context with `credentials: "include"` and parse it with `DOMParser`. It may not invent the URL.

### 3. Return lifecycle is secondary enrichment

A normal order is not a return. `Return or replace items`, `Start a return`, or return eligibility alone must never create a return.

A real existing return-status URL such as `/spr/returns/prep?...` discovered from Order Details may be followed only for that same Amazon Order ID to refresh return lifecycle data.

Bulk detail refresh follows real `/spr/returns/prep` links through the authenticated Amazon session and parses the returned HTML. The explicit per-order dashboard **Refresh** action uses a separate rendered inactive/background Amazon tab as the stronger manual recovery path.

Return lifecycle remains evidence-based:

`Initiated -> Dropped off / shipped -> Amazon received -> Refund issued -> Bank credited`

- Static timeline labels are not completion evidence by themselves.
- `Refund issued` requires affirmative Amazon issuance wording.
- A future `credited by <date>` value is stored/displayed as an ETA, never as completed credit.
- Return stage merge is monotonic; stale scans cannot regress a later authoritative stage.
- Bank credit confirmation remains separate from Amazon lifecycle state.

### 4. Bundled / multi-item returns

Return records are item-level under one canonical order.

v0.17 return record identity includes the return token plus the returned item identity, allowing multiple returned items and multiple separate returns under one Amazon Order ID.

Rules:

- The returned item title/ASIN must come from return-scoped evidence.
- A provisional return discovered from an Order Details status link must not copy all bundled order items and pretend they were returned.
- When an authoritative return page arrives, provisional item names/ASINs are replaced by the authoritative returned-item data.
- If multiple returned items are present, each record gets its own locally scoped expected-refund amount when Amazon exposes it.
- A whole return/order total must not be duplicated onto every returned item. If an item-specific amount cannot be proven for a multi-item return, leave that item's amount unknown rather than assigning the bundle total.

### 5. Payment-card last four

Card last-four extraction is restricted to payment-method/payment-information evidence.

- DOM parsing first collects payment-scoped elements.
- If Amazon lacks useful payment selectors, a narrow local text window beginning at `Payment method` or `Payment information` may be used.
- Whole-page text is not used as a fallback during document parsing.
- Arbitrary masked four-digit text elsewhere on the page must remain ignored.

### 6. Dashboard

Primary views remain:

- `All orders`
- `Returns`
- `Needs review`

Every order uses the same fixed row/grid structure. Rows do not become horizontally scrollable.

Every row has the same four side-by-side actions:

- `Details`
- `Credit`
- `Reset`
- `Refresh`

Inapplicable actions are disabled rather than removed so the grid remains symmetric.

`Refresh`:

1. requires the stored real Order Details URL,
2. opens an inactive Amazon Order Details tab,
3. parses the rendered canonical detail page,
4. requires a complete matching canonical capture,
5. follows real `/spr/returns/prep` links for the same order when present,
6. saves authoritative return records,
7. closes the temporary refresh tab.

`Needs review` dollar total is the sum of expected refund amounts for the return records currently flagged Needs Review.

### 7. Development reset policy

During active development `DEV_RESET_ON_VERSION_CHANGE` is enabled in `background.js`.

On an extension version change, v0.17 clears local ledger/crawl/worker/workflow/bank-verification state and stores the new manifest version. The `runtime.onInstalled` previous-version hint is used so an upgrade from v0.16 resets correctly even though v0.16 did not yet store the new version key.

Disable or replace this destructive development behavior with migrations before a production release where users expect ledger persistence across versions.

### 8. Bank reconciliation privacy boundary

Bank credentials, financial-provider tokens, and full bank transaction feeds never enter the extension.

The supported bridge remains narrow:

1. extension exports refund verification request JSON,
2. reconciliation occurs outside the extension against separately connected financial accounts,
3. extension imports narrow verification-result JSON.

Only posted/confirmed evidence completes `Bank credited`. Pending, ambiguous, or not-found matches do not.

## Current source structure

- `manifest.json` — MV3 manifest, version 0.17.0.
- `background.js` — queue, strict crawl state machine, fingerprint validation, rendered per-order refresh, development version reset.
- `content.js` — Amazon page scan, authenticated canonical detail fetch, real return-status enrichment.
- `parser.js` — history/detail/return parsing, payment scoping, item-level return parsing.
- `storage.js` — canonical ledger merge, monotonic return state, provisional-to-authoritative return replacement, reconciliation state.
- `dashboard.html` / `dashboard.js` / `ui.css` — fixed compact order grid and four-action row layout.
- `popup.html` / `popup.js` — compact extension status/menu.
- `workflow-recorder.js` — Teach Mode diagnostics; do not commit real account logs.
- `parser-test.js`, `storage-test.js`, `background-test.js`, `state-machine-test.js`, `reconciliation-test.js`, `ui-test.js` — regression suites.

## Automated validation

Run:

```bash
npm test
```

v0.17.0 test command executes:

- `node parser-test.js`
- `node storage-test.js`
- `node background-test.js`
- `node state-machine-test.js`
- `node reconciliation-test.js`
- `node ui-test.js`

The v0.17 candidate passed the complete suite in GitHub Actions before release review.

Important v0.17 regression coverage includes:

- no synthesized canonical Order Details URL,
- visible Order IDs remain independent from discovered detail links,
- URL-only pagination change is rejected,
- missing real detail link stops managed crawl,
- unrelated four-digit text is not a payment card,
- payment scope does not fall back to whole-page text,
- future credit ETA does not become completed credit,
- item-level return IDs and refund amounts,
- authoritative return capture replaces provisional bundled-item contamination,
- version-change clean reset, including v0.16 -> v0.17 with no prior version key,
- fixed Details / Credit / Reset / Refresh UI and enlarged click targets,
- no horizontal order scrolling.

## Required live Amazon Business acceptance for v0.17

Still verify on the user's actual Amazon Business account:

1. Start with a clean v0.17 ledger after reload/update.
2. 2026 page 1 -> page 2 -> page 3 advances with different visible Order-ID fingerprints.
3. The crawler does not switch to 2025 while an enabled 2026 Next control exists.
4. A repeated page/fingerprint stops or retries instead of counting progress.
5. Every row labeled `Detailed` came from a complete matching real Order Details URL.
6. Missing real `View order details` anchors stop the crawler rather than fabricating URLs.
7. Card last four matches Amazon payment-method/payment-information evidence only.
8. A normal order with only `Return or replace items` stays a normal order.
9. A real existing `/spr/returns/prep` link updates the same order's return lifecycle.
10. An in-progress return never displays `Refund issued` without affirmative Amazon issuance evidence.
11. Bundled orders show only the actual returned product(s) and item/return-specific expected refund amounts.
12. Two separate returns under one Amazon Order ID remain separate records.
13. Per-order `Refresh` opens an inactive detail tab, updates rendered detail/return state, and closes the tab.
14. All rows remain symmetric with four side-by-side actions and no horizontal order-container scrolling.
15. Needs Review total equals the expected-refund sum of currently flagged return records.

## Security / privacy

Never commit real Amazon exports, Order IDs used as private fixtures, addresses, authentication/session data, payment numbers, bank data, reconciliation request/result files, or real Teach Mode logs.

Do not add CAPTCHA bypass, stealth/anti-detection behavior, cookie/password harvesting, or bank credentials.

## Recovery

The historical exact v0.16.0 packaged ZIP remains archived at `source-snapshots/v0.16.0/full/` with documented SHA-256:

`0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42`

It is recovery/audit material only. Do not replace the complete v0.17 root tree with v0.16 unless the current root is proven corrupt and the rollback is intentional.

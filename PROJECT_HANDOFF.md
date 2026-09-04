# Project Handoff — Amazon Order Manager

## Current baseline

Chrome Manifest V3 Amazon / Amazon Business Order Manager and Refund Ledger.

**Current source baseline: v0.18.3 candidate for Issue #17.** Root source remains the active development source. The exact pre-GitHub v0.16.0 archive under `source-snapshots/v0.16.0/full/` is historical recovery material only.

v0.18 preserves the complete v0.17 Amazon crawler/details/returns/dashboard contract and adds a verified Windows development auto-update channel.



## v0.18.3 live acceptance fixes

Issue #17 captures the next live defects from v0.18.2. The strict crawler now accepts Amazon-supplied legacy `/gp/css/summary/edit.html?orderID=...` as a real detail route while continuing to forbid synthesized URLs; a genuine missing link names its exact Order ID. Return identity uses stable `returnItemId` as the binding, preserves exact Order Details titles, and only flags identity conflict for contradictory non-empty ASIN evidence. Dashboard child-return item text is sourced from trusted Order Details bindings when available. `extractStatusText` is now stage-aware, so static `Refund issued` timeline labels cannot advertise a refund milestone that `parseReturnMilestones` has not affirmatively proven. Badge wrapping prevents long review labels from overlapping the order column.

v0.18.3 must be used to prove unattended update from repaired v0.18.2; no manual extension reload/replacement is allowed for that acceptance.

## v0.18.2 live multi-return + updater reliability release

Live Amazon Business testing exposed two defects after v0.18.1:

1. one Order ID with several independent return-status links was flattened into repeated/blended return rows, including the same wrong product title and an impossible aggregate refund greater than Amazon's canonical Order Details Refund Total;
2. the installed v0.18.0 development copy did not update itself to the published v0.18.1 prerelease.

PR #16 implements v0.18.2.

### Return hierarchy

The durable model is now:

`order -> return group -> returned item(s)`

- Return group identity: Amazon `rmaId` / `contractId` / normalized return token.
- Returned-item identity: Amazon return-link `itemId`, with ASIN/title as supporting evidence.
- Exact Order Details return-link item binding is trusted because it is physically scoped to the returned product block.
- A later authoritative return page enriches lifecycle/refund evidence but may not silently replace conflicting trusted item identity; conflicts set `itemIdentityConflict` and require review.
- Provisional and authoritative captures for the same `returnToken + itemId` intentionally share one record ID.
- Redirects that strip query identity are repaired by carrying the original return-link token/item/contract/RMA hint into a single authoritative child capture.
- Explicit return links suppress the extra broad strong-text provisional return on Order Details.
- Per-order Refresh follows every unique same-order return child separately.

### Refund accounting

Order Details' explicit standalone `Refund Total` is the only canonical order-level refund source. Generic phrases such as `refund has been issued $X` are lifecycle evidence, not canonical order totals.

Return records distinguish item-scoped and return-group-scoped amounts. A group amount is counted once; item amounts are summed only when item scope is proven. The dashboard prefers canonical `Refund Total`, displays unknown amounts as `—`, flags child/group conflicts and aggregates that exceed canonical Refund Total, and uses canonical expected refund for integrity-review totals.

### Updater reliability

The earlier v0.18.0 -> v0.18.1 unattended path failed live and is not considered validated. v0.18.2 therefore:

- initializes the updater whenever the MV3 service worker boots,
- recreates/verifies its 15-minute alarm,
- also checks at Chrome startup and via a popup `Check development update now` action,
- persists current/latest/host/check/install/reload/error diagnostics,
- calls `chrome.runtime.reload()` synchronously after a verified newer install rather than from a delayed timer,
- writes native-host diagnostics to `%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\updater.log`,
- supports native-host `--self-test`,
- adds `Install.ps1 -DiagnoseOnly`, compatible with Windows PowerShell 5.1.

Because the old channel did not self-repair, v0.18.2 requires one explicit updater/bootstrap repair on the Windows test PC. A later version must prove unattended update from v0.18.2 before Issue #10 closes.

Live tracking:

- Issue #7 — Amazon Business product acceptance.
- Issue #10 — unattended updater proof remains open.
- Issue #13 — v0.18.2 architecture/acceptance.
- Issue #15 — v0.18.2 Windows repair + multi-return live retest.

## v0.18.1 live payment-card regression fix

Live Amazon Business testing of v0.18.0 exposed repeated incorrect `Card •••• 1000` values across unrelated orders. The root cause was generic DOM selectors whose id/class/data-testid contained `card`; Amazon uses `card` for non-payment layout components, so unrelated masked values could contaminate payment evidence.

v0.18.1 changes the invariant to: card last-four is accepted only from payment/refund-method-specific evidence and must be directly tied to a recognized payment-card instrument or an immediately masked value under an explicit Payment/Refund method heading. Gift-card/generic masked values are rejected. Provisional return records inherit the already-scoped canonical order card value rather than reparsing broad order context.

`payment-evidence-test.js` reproduces the false `1000` case and protects legitimate Visa/Mastercard/refund-method parsing. Because development version changes intentionally reset the ledger, the v0.18.1 auto-update starts with clean state so stale v0.18.0 card values do not survive the retest.

Two live-validation tracks remain separate:

- **Issue #7** — live Amazon Business acceptance of the v0.17 authoritative Amazon behavior. The code/test scope is implemented; real account-specific markup still requires live acceptance.
- **Issue #10** — v0.18 verified development auto-update pipeline. Code/tests/CI are implemented; the Windows bootstrap and one subsequent real automatic update must be live-validated before closure.

## v0.18 development auto-update architecture

### Purpose

Eliminate the repetitive unpacked-extension cycle of downloading a ZIP, copying files, and manually pressing Reload after every revision, without allowing the extension to download/execute remote JavaScript or weakening MV3 security.

### Stable development identity

The development manifest contains a public `key` so the unpacked extension has a stable ID:

```text
hhmimkpolikhncnbkkbbabbopbccabcf
```

Native host name:

```text
com.supremefabworks.amazon_order_manager_updater
```

Allowed native-messaging origin:

```text
chrome-extension://hhmimkpolikhncnbkkbbabbopbccabcf/
```

Protocol:

```text
arl-dev-updater-v1
```

The private RSA material used to derive the public manifest key is not required by the development runtime and must never be added to the repository.

### Extension side

`manifest.json` uses `service-worker.js` as the service worker. The wrapper imports:

```text
background.js -> existing Amazon/order/crawl behavior
dev-updater.js -> development update bridge
```

`dev-updater.js`:

- uses `nativeMessaging`,
- checks on MV3 worker startup, Chrome startup, manually from the popup, and every 15 minutes,
- sends only updater protocol/version/extension-ID/reason metadata to the native host,
- records update diagnostics under `devUpdateStatus`,
- treats missing host, network failure, invalid response, or host error as non-fatal,
- calls `chrome.runtime.reload()` synchronously only when the host reports a successful install whose version is strictly newer than the currently running manifest version,
- uses its own alarm name and does not enqueue Amazon crawl jobs.

### Windows native host

`tools/dev-updater/NativeHost.cs` is a small .NET Framework native messaging host.

It:

1. requires Chrome's caller origin to exactly match the fixed development origin,
2. requires the request extension ID to match the fixed development ID,
3. queries this repository's public GitHub releases,
4. considers only non-draft prereleases tagged `dev-v<Chrome numeric version>`,
5. selects the highest valid version,
6. does nothing unless that version is strictly newer than the running extension,
7. requires both `amazon-order-manager.zip` and `amazon-order-manager.zip.sha256`,
8. downloads both over HTTPS,
9. verifies SHA-256 before extraction,
10. verifies the embedded manifest version matches the GitHub release tag,
11. verifies required extension files exist,
12. stages files in a `.next-*` directory,
13. moves the current successful build to `previous`,
14. promotes the staged build to `current`,
15. attempts rollback if the swap fails,
16. reports success only after the verified install finishes.

No Amazon credentials, cookies, passwords, bank credentials, financial-provider tokens, or bank transaction feeds are sent to this host.

### One-time Windows bootstrap

CI publishes `amazon-order-manager-dev-updater.zip`, containing:

- `Install.ps1`
- `NativeHost.cs`
- updater README

Run once:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

Default installation root:

```text
%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev
```

Permanent unpacked Chrome directory:

```text
%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\current
```

The installer compiles the native host with Windows PowerShell/.NET Framework, registers it under HKCU for Chrome, downloads the latest verified development release, validates it, and installs `current`.

The user must then perform one final manual migration in `chrome://extensions`: remove the older unpacked copy and load this fixed `current` directory. After that, do not manually overwrite `current`.

### CI/release flow

`.github/workflows/ci.yml` runs on PRs and main pushes.

For every candidate it:

1. verifies required source files exist,
2. runs `npm test`,
3. packages `amazon-order-manager.zip`,
4. writes `amazon-order-manager.zip.sha256`,
5. packages `amazon-order-manager-dev-updater.zip`,
6. uploads all three as an Actions artifact.

For successful pushes to `main`, it publishes a GitHub prerelease tagged:

```text
dev-v<manifest version>
```

If that tag already exists for the same commit, a workflow rerun succeeds idempotently. If the tag exists for a different commit, CI fails. Therefore **every user-testable revision must bump both `manifest.json` and `package.json` to the same strictly newer version**.

### Production boundary

The following are development-only and must not silently become the production distribution architecture:

- local Native Messaging updater,
- development manifest ID/key policy,
- destructive `DEV_RESET_ON_VERSION_CHANGE` behavior.

Before Chrome Web Store production release, disable/remove the local updater, replace destructive resets with explicit data migrations, preserve ledger state across normal upgrades, and use the Chrome Web Store update channel.

## Product contract preserved from v0.17

### 1. Strict lifetime crawler

Required sequence:

`newest year -> page 1 -> capture every visible unique Order ID -> complete canonical Order Details for every order -> next page -> repeat until no more pages -> next older year`

Rules:

- Never switch years while Amazon still exposes an enabled next-page control.
- Pagination progress is accepted only when the visible non-empty Order-ID fingerprint changes.
- URL/hash changes without a fingerprint change are not progress.
- Repeated page contents are failed pagination and stop/retry at the same checkpoint.
- Keep exact year/page/order checkpoint state.
- Deduplicate globally by Amazon Order ID.
- Repeated orders are overlap evidence, not duplicate canonical records.
- A visible history Order ID with no real `View order details` URL is a hard crawler stop. Never synthesize a canonical detail URL.

Observed Amazon Business hash routes include:

- `#time/2026/pagination/1/`
- `#time/2026/pagination/2/`
- `#time/2026/pagination/3/`

Prefer Amazon's real numbered pager / Next control. Legacy query pagination is compatibility-only for query-routed non-Business pages.

### 2. Order Details is canonical

Every order retains the real Amazon `View order details` URL discovered from history.

Canonical detail parsing succeeds only when:

- the page is an Amazon Order Details route,
- URL Order ID matches the order being captured,
- order date is captured,
- finite order total is captured,
- at least one item title is captured.

Only then may `detailScanComplete=true` / `Detailed` be displayed.

### 3. Return lifecycle is secondary enrichment

A normal order is not a return. `Return or replace items`, `Start a return`, or return eligibility alone never creates a return.

A real existing return-status URL such as `/spr/returns/prep?...` discovered from Order Details may be followed only for the same Amazon Order ID.

Lifecycle remains evidence-based and monotonic:

`Initiated -> Dropped off / shipped -> Amazon received -> Refund issued -> Bank credited`

- Static timeline labels are not completion evidence by themselves.
- `Refund issued` requires affirmative Amazon issuance wording.
- A future `credited by <date>` is an ETA, not completed credit.
- Bank credit confirmation remains separate from Amazon lifecycle state.

### 4. Bundled / multi-item returns

Return records are item-level beneath one canonical order.

- Returned title/ASIN must come from return-scoped evidence.
- Provisional return discovery must not copy every bundled item and claim they were returned.
- Authoritative return captures replace provisional item identity.
- Each returned item gets only its own locally scoped expected refund when proven.
- Whole-order/whole-return totals must not be duplicated across returned items.
- Multiple separate returns under one Amazon Order ID remain distinct records.

### 5. Payment-card last four

Card last-four extraction is restricted to payment-method/payment-information evidence. Whole-page arbitrary four-digit text is not a fallback.

### 6. Dashboard / Refresh

Primary views:

- `All orders`
- `Returns`
- `Needs review`

Every order uses the same fixed grid with side-by-side:

- `Details`
- `Credit`
- `Reset`
- `Refresh`

Inapplicable actions are disabled rather than removed. Rows do not become horizontally scrollable.

Per-order `Refresh` requires the stored real Order Details URL, opens an inactive Amazon detail tab, parses a complete matching canonical capture, follows real same-order return links when present, saves authoritative results, and closes the temporary tab.

Needs Review dollars are the expected-refund sum of return records currently flagged Needs Review.

### 7. Development reset policy

`DEV_RESET_ON_VERSION_CHANGE` remains enabled during active development. A version change clears local ledger/crawl/worker/workflow/bank-verification state and records the new version. v0.18 therefore intentionally starts clean when moving from v0.17.

### 8. Bank reconciliation privacy boundary

Bank credentials, provider tokens, and full bank transaction feeds never enter the extension.

Supported bridge:

1. extension exports narrow refund-verification request JSON,
2. reconciliation occurs outside the extension against separately connected financial accounts,
3. extension imports narrow verification-result JSON.

Only posted/confirmed evidence completes `Bank credited`.

## Current source structure

- `manifest.json` — MV3 manifest, v0.18.0, fixed development ID, nativeMessaging permission.
- `service-worker.js` — imports core background worker then development updater bridge.
- `background.js` — queue, strict crawl state machine, fingerprint validation, rendered per-order refresh, development version reset.
- `dev-updater.js` — native-host update check/reload coordination.
- `content.js` — Amazon page scan, authenticated canonical detail fetch, real return-status enrichment.
- `parser.js` — history/detail/return/payment parsing.
- `storage.js` — canonical ledger merge, monotonic return state, reconciliation state.
- `dashboard.html` / `dashboard.js` / `ui.css` — fixed compact ledger UI.
- `popup.html` / `popup.js` — compact status/menu.
- `workflow-recorder.js` — Teach Mode diagnostics; never commit real account logs.
- `tools/dev-updater/NativeHost.cs` — Windows native updater host.
- `tools/dev-updater/Install.ps1` — one-time Windows bootstrap.
- `parser-test.js`, `storage-test.js`, `background-test.js`, `state-machine-test.js`, `reconciliation-test.js`, `ui-test.js`, `dev-updater-test.js`, `release-test.js` — regression suites.

## Automated validation

Run:

```bash
npm test
```

v0.18 adds updater/release regressions to the six v0.17 suites. Important updater coverage includes:

- manifest/package version parity,
- fixed extension ID derived from manifest key,
- host/origin constant consistency,
- 15-minute alarm scheduling,
- reload only after strictly newer successful install,
- invalid/missing host responses fail closed,
- CI checksum/release asset invariants.

The Windows native host compiler/runtime and registry integration cannot be proven by Linux CI; those remain explicit live acceptance items in `TESTING.md`.

## Required live acceptance

### Issue #7 — Amazon Business

Use the complete `TESTING.md` checklist. At minimum verify strict same-year pagination, complete real canonical detail links, evidence-only payment/returns/refunds, bundled item-level returns, per-order background Refresh, symmetric dashboard rows, and Needs Review totals.

### Issue #10 — development auto-update

After v0.18 merge/main CI:

1. verify `dev-v0.18.0` contains the extension ZIP, SHA sidecar, and updater ZIP,
2. run the one-time Windows bootstrap,
3. load the fixed `current` directory once and verify the fixed extension ID/version,
4. verify normal extension operation with no update available,
5. later merge a strictly newer test version,
6. do not manually copy/reload files,
7. verify the host installs the newer verified package and Chrome reloads automatically,
8. verify `previous` contains the prior build and current functionality remains healthy.

Issue #10 stays open until that real two-version path passes.

## Security / privacy

Never commit real Amazon exports, private Order IDs used as fixtures, addresses, authentication/session data, payment numbers, bank data, reconciliation request/result files, real Teach Mode logs, native-host secrets, or private signing keys.

Do not add CAPTCHA bypass, stealth/anti-detection behavior, cookie/password harvesting, bank credentials, or remote-code execution inside the extension updater.

## Recovery

The historical exact v0.16.0 package remains archived under `source-snapshots/v0.16.0/full/` with SHA-256:

`0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42`

It is recovery/audit material only. Do not replace the complete v0.18 root with v0.16 unless current root is proven corrupt and rollback is intentional.


## v0.18.5 terminal cancelled-order handling

Live v0.18.3 stopped on 2026 page 6 because order `112-3886192-2097013` is explicitly Cancelled, totals `$0.00`, and has no real Order Details link. v0.18.5 treats only that strongly proven terminal history-card shape as complete for the crawl gate without setting `detailScanComplete`. Normal missing-detail orders still stop. Issue #19 is the live tracker. The second PC should test unattended `0.18.3 -> 0.18.4` update; do not reinstall or manually Reload for that proof.


### v0.18.5 live fixes
- Structural single-order history-card locator handles orders with no Detail anchor without neighboring-order contamination.
- `$0.00` terminal cancelled exception remains strict and now receives the correct scoped card.
- Broad return-page product links no longer create ASIN identity; only directly bound item ASIN evidence may conflict with trusted Order Details identity.
- Live examples motivating the identity fix: RAMPOW order `111-1110034-5588263` and Milton order `111-8528386-2632255`.


## v0.18.6 live boundary fix
- Live v0.18.5 reached 2026 page 18 with 7/7 orders complete but mistook disabled Next for an actionable pager and stopped instead of switching years.
- v0.18.6 scopes Next detection to real pagination controls/numeric pagination routes. Final selected page + disabled/no actionable Next = year complete -> next older year.
- Page fingerprint remains the only proof of a successful within-year advance.
- Issue #23 remains open until a live lifetime scan crosses 2026 page 18 into 2025.


## v0.18.7 implementation
- Live ThermoMaven order `111-1790078-4741015` proved static return timeline labels/policy prose could falsely promote Dropped off / Return received. v0.18.7 moves milestone completion to affirmative evidence, with DOM checkmarks as structured supplemental evidence.
- Crawl pacing is ~30% faster through shorter serial delays only; rate-limit and correctness gates are unchanged.
- Canonical Order Details now stores structured purchased `orderItems`; UI joins return groups per purchased product and displays all purchased products, including non-returned ones.
- Issue #25 tracks live acceptance. Issue #23 remains separate until year rollover is observed live.


## v0.18.8 live return-state fix
- Breville `113-1426991-3716216`: Amazon shows completed Initiated Aug 7, Dropped off Aug 31, Return received Sep 2; Refund issued Sep 10 and Refund credited Sep 17 are future unchecked labels.
- v0.18.8 adds explicit Return received UI/storage, ordered-prefix milestone checkmark interpretation, and strict separation of Amazon lifecycle vs bank verification.
- Bank-before-refund-issued becomes Needs Review instead of Credited. Issue #27 tracks live acceptance.

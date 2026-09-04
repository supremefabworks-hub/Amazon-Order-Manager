# Amazon Order Manager

Chrome Manifest V3 extension for building a local Amazon / Amazon Business order and refund ledger from the authenticated browser session.

**Current source baseline: v0.18.15 candidate for Issue #41.** GitHub is the source of truth and chat sessions are disposable.

Current live acceptance trackers:

- **#7 — live Amazon Business acceptance** for the authoritative crawler/return behavior.
- **#23 — final-page year rollover acceptance** proving a disabled `Next` ends the current year and starts the next older year.
- **#25 — v0.18.7 acceptance** for faster serial crawl pacing and per-product order status.
- **#29 — v0.18.9 acceptance** for authoritative return progress and complete-only ledger behavior.
- **#31 — v0.18.10 acceptance** for consolidated dashboard metrics and four user-facing views: Orders, Returns, Return review, Errors.
- **#33 — v0.18.11 acceptance** for replacement detection and replacement-vs-return separation.
- **#35 — v0.18.12 acceptance** for adaptive smart-fast serial crawl pacing and rate-limit safety.
- **#37 — v0.18.13 acceptance** for combined Reset & Refresh and live installed-version display.
- **#39 — v0.18.14 acceptance** for durable checkpoint resume, ledger-backed overlap recovery, and opt-in Amazon Auto-start.

Updater Issue **#10 is closed** after unattended live update from v0.18.3 to v0.18.4 succeeded on the second Windows PC.

## Start a completely new chat

Use [`NEW_CHAT_PROMPT.md`](NEW_CHAT_PROMPT.md). `SESSION_PROTOCOL.md` defines mandatory startup/handoff behavior and `AGENTS.md` requires contributors to reconstruct state from GitHub rather than chat history.

## Resume development

1. Read `AGENTS.md`, `PROJECT_HANDOFF.md`, `README.md`, `TESTING.md`, and `SESSION_PROTOCOL.md`.
2. Read Issues #7, #23, #25, #29, #31, #33, #35, #37, and #39 and any newer issue that supersedes their scope.
3. Inspect root source, `manifest.json`, recent commits, open PRs/issues, and tests before editing.
4. Root v0.18.15 is the active candidate. The archived v0.16.0 ZIP is recovery material only.
5. Run `npm test` before packaging or merging changes.
6. Every user-testable development revision must bump both `manifest.json` and `package.json` to the same newer Chrome version.
7. Keep implementation, regression tests, docs, issue state, and handoff synchronized.

## Development auto-update channel

v0.18 removes the repeated manual download/copy/reload cycle for the local unpacked development extension.

### One-time Windows bootstrap

The GitHub development release includes `amazon-order-manager-dev-updater.zip`. Extract it and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

The installer places the development extension at:

```text
%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\current
```

Then, one time only, open `chrome://extensions`, enable Developer mode, remove any older unpacked copy, choose **Load unpacked**, and select that exact `current` folder.

The fixed development extension ID is:

```text
hhmimkpolikhncnbkkbbabbopbccabcf
```

Do not manually replace files inside `current`; the verified native updater owns that directory.

### Normal revision flow after bootstrap

`code change -> regression tests -> manifest/package version bump -> PR CI -> merge to main -> CI publishes dev-v<version> prerelease -> installed extension checks updater -> verified files replace current -> chrome.runtime.reload()`

The v0.18.0 -> v0.18.1 unattended update did **not** succeed in live Windows testing, so that earlier path is not considered validated. v0.18.2 checks whenever the MV3 service worker starts, at Chrome startup, manually from the popup, and every 15 minutes. It recreates its important alarm, records updater diagnostics, and reloads synchronously only after the native host confirms a verified newer install. A missing native host, GitHub/network failure, digest mismatch, invalid package, or failed install leaves the current build running and exposes a diagnostic instead of reloading.

The native host downloads only the versioned GitHub development extension ZIP and its SHA-256 sidecar. It verifies the digest, embedded manifest version, and required files before replacing the current build. It is restricted to the fixed development extension origin and does not receive Amazon credentials, cookies, passwords, bank credentials, or bank-provider tokens.

Main-branch CI will not silently overwrite an existing `dev-v<version>` release for a different commit. A new user-testable revision therefore requires a version bump.

### Production boundary

The native updater, stable development ID policy, and destructive development version reset are development-only. Before a production Chrome Web Store release:

- disable/remove the local native updater,
- replace destructive version resets with data migrations,
- preserve ledger data across normal upgrades,
- use Chrome Web Store distribution/update mechanisms.



## v0.18.3 live acceptance hardening

v0.18.3 addresses live Amazon Business findings after v0.18.2: captured legacy `/gp/css/summary/edit.html?orderID=...` links are accepted as real canonical Order Details routes; strict missing-link failures now name the exact Order ID(s); same-`itemId` title variation no longer creates false item conflicts unless non-empty ASIN evidence contradicts; dashboard return-group identity prefers the exact Order Details return-link binding; and bare static `Refund issued` timeline labels cannot appear as affirmative refund-issued status text. Long status badges wrap within the fixed column.

The updater path introduced here was later proven live by an unattended v0.18.3 -> v0.18.4 update on the second Windows PC.

## v0.18.2 multi-return model

A single Amazon Order ID may contain multiple independent returns. v0.18.2 models them explicitly as:

`order -> return group (rmaId / contractId) -> returned item(s) (itemId)`

- Every real Order Details `View return/refund status` link is bound to its nearest product block rather than to the whole order.
- `itemId` is the stable returned-item identity. `rmaId`/`contractId` identify the return group.
- The Order Details return-link item binding is trusted; a conflicting return-page title/ASIN is flagged for review rather than silently replacing it.
- Provisional Order Details evidence and the later authoritative return page use the same stable child record identity.
- If explicit return links exist, the parser does not add an extra broad order-level provisional return.
- The dashboard renders separate compact `Return X of N` child blocks rather than repeating the full order catalog for every lifecycle.
- Unknown child refund money displays `—`, never `$0.00`.

### Refund accounting

Amazon Order Details remains canonical for the order-level refund amount. Only the explicit standalone `Refund Total` label may populate `canonicalRefundTotal`. Generic refund lifecycle prose is not an order-level total.

The dashboard therefore:

- displays canonical Order Details `Refund Total` when available,
- counts a return-group amount only once,
- sums child item amounts only when item scope is proven,
- flags conflicting group amounts or a child aggregate that exceeds canonical Refund Total,
- uses the canonical expected refund for Needs Review totals when an integrity mismatch is present.

### v0.18.2 updater repair

Because the prior installed channel did not update itself from v0.18.0 to v0.18.1, install the v0.18.2 updater/bootstrap package once on the Windows test PC to repair the channel. The popup now exposes updater current/latest/check/error state and **Check development update now**. The native host writes `updater.log` under the updater install root, supports `--self-test`, and `Install.ps1 -DiagnoseOnly` runs local diagnostics.

Issue #10 is closed: the repaired channel later completed an unattended v0.18.3 -> v0.18.4 update on the second Windows PC without reinstalling or manually reloading the extension.

## Core v0.17/v0.18 product architecture

v0.18.1 does not loosen the v0.17 Amazon data contract. It additionally hardens payment-card last-four capture so generic Amazon layout `card` containers, gift-card values, and unrelated masked numbers cannot become canonical card evidence.

### Canonical orders

- Every normal visible history order must resolve to a real Amazon `View order details` URL.
- The extension never synthesizes missing canonical detail URLs.
- During resume/recovery, a previously captured real canonical Order Details URL may be reused for the same known Order ID if the current history card temporarily omits its action. This is stored Amazon evidence, not URL synthesis.
- A managed crawl stops if a normal visible Order ID has neither a current real detail link nor a previously captured real canonical Detail URL.
- `Detailed` means a complete matching canonical detail capture, not merely a discovered order or a detail-shaped URL.

### Strict lifetime crawler

Crawler order is mandatory:

`newest year -> page 1 -> every visible order -> every canonical detail -> next page -> ... -> next older year`

- Never switch years while an enabled next-page control exists.
- Accept pagination only when the non-empty visible Order-ID fingerprint changes.
- URL/hash changes alone are not progress.
- Repeated page contents are failed pagination.
- Preserve exact checkpoint state and globally deduplicate by Order ID.
- Repeated orders across pages are stored as overlap evidence.

### Returns

- `Return or replace items` alone is never evidence of a return.
- A real `/spr/returns/prep` link discovered from Order Details may be followed only for that same order as secondary lifecycle enrichment.
- Return stages are evidence-based and monotonic.
- A future credit date is an ETA, not a completed credit.
- Bundled/multi-item returns are stored as item-level records; whole-order totals are not duplicated onto each returned item.
- Multiple separate returns may exist under one Amazon Order ID.

### Payment card last four

Card last four is extracted only from payment-method/payment-information evidence. Whole-page arbitrary four-digit text is not a fallback.

### Per-order recovery and dashboard

Every row uses the fixed `Details | Credit | Reset & Refresh` action group. `Reset & Refresh` clears derived data for that Order ID while preserving only the real captured Order Details route, then rebuilds canonical Order Details and legitimate same-order return children in an inactive Amazon tab. Failures remain visible in Errors with the real route preserved, and the temporary tab is always closed before the serial worker lock is released.

User-facing completed-data views are exactly `Orders`, `Returns`, `Return review`, and `Errors`. Incomplete non-error orders remain internal/hidden until complete. No order container may scroll horizontally. Return review dollars equal the expected-refund sum for return records currently flagged for review.

### Development state migration policy

As of v0.18.14, development version updates preserve canonical ledger data, bank verification evidence, and the exact lifetime-crawl checkpoint. The updater may clear/close stale transient worker-tab identity, then resumes active unpaused work from the persisted current job/year/page/fingerprint. Earlier v0.18 builds intentionally used destructive version resets; that policy is superseded and must not be reintroduced.

## Validation

Run:

```bash
npm test
```

The suite covers parser, storage, background navigation, strict crawl state, reconciliation, UI, development updater behavior, and release invariants. See `TESTING.md` and `PROJECT_HANDOFF.md` for live acceptance checklists.

## Privacy / security

The extension must never receive bank credentials, financial-provider tokens, password/session exports, or full bank transaction feeds. Bank reconciliation remains the narrow JSON bridge documented in the repository.

Do not add CAPTCHA bypass, stealth/anti-detection behavior, cookie/password harvesting, committed real-account Amazon/Teach Mode data, or updater logic that downloads and executes remote JavaScript inside the extension.

## Recovery archive

The exact pre-GitHub v0.16.0 ZIP remains under `source-snapshots/v0.16.0/full/` for recovery/audit only.

Documented SHA-256:

`0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42`


## v0.18.5 terminal cancelled-order handling

Amazon can render a fully cancelled `$0.00` order in Order History without any `View order details` URL. v0.18.5 adds a narrow terminal-history exception: only a scoped history card proving the same Order ID, an exact `Cancelled`/`Canceled` state, an exact `$0.00` total, and no real Order Details link may satisfy the managed crawl page gate. It is saved with `historyTerminalComplete=true` / `historyTerminalState=cancelled`, remains `detailScanComplete=false`, counts toward lifetime unique-order completion, and renders as `Cancelled` / `Terminal history` with Details and Reset & Refresh disabled. Any normal, ambiguous, nonzero, or unknown-total missing-link order still hard-stops the crawler rather than inventing a URL.

Issue #19 tracks live acceptance using order `112-3886192-2097013` as the observed case. This release is also intended as the automatic updater test from a fresh v0.18.3 installation on the second Windows PC.


## v0.18.5 live structural-scoping hardening

v0.18.5 fixes two live parser defects. Orders with no Detail action, especially proven `$0.00` cancelled orders, are now scoped by their own structural Order History card using the visible Order ID and single-order ancestor boundaries instead of falling back to neighboring page text. Return-page identity is also hardened: whole-page/broad-section product links cannot manufacture returned-item ASINs; contradictory ASIN evidence is reviewable only when directly bound to the return item through a specific item block/data-ASIN or direct product anchor. Stable Amazon `returnItemId` plus trusted Order Details identity remains authoritative.


## v0.18.6 end-of-year pagination boundary

v0.18.6 treats Amazon history pagination as a scoped control state, not generic page text. A selected final page with disabled/no actionable Next now marks that year complete and queues the next older discovered year. Enabled Next or a concrete numeric N+1 pagination target still advances only after the visible Order-ID fingerprint changes. Generic unrelated `Next` text cannot keep a year alive.


## v0.18.7 evidence-safe milestones, faster serial crawl, and per-product state

- Return milestones now require affirmative completion evidence or an item-scoped Amazon timeline checkmark; future instructions, policy prose, and static labels do not advance lifecycle state.
- Normal serial crawl idle/settle intervals are approximately 30% shorter. Concurrency, retry counts, rate-limit cooldowns, canonical Detail requirements, and Order-ID fingerprint gates are unchanged.
- Canonical Order Details now persists structured `orderItems`. The dashboard remains one card per order but shows every purchased product beneath it, with product-scoped quantity/price/fulfillment fields only when directly proven. Return groups join to purchased products by strong ASIN or conservative long-title evidence; non-returned products remain visible as `Not returned`, and unmatched returned children stay visible for review.


## v0.18.8 Amazon lifecycle / bank separation
Amazon return lifecycle is five explicit stages: Initiated -> Dropped off -> Return received -> Refund issued -> Refund credited. Amazon milestone checkmarks complete the leading timeline stages; future unchecked labels remain pending. Bank verification is independent and never promotes Amazon stage. A bank-confirmed credit before Amazon shows Refund issued is a review conflict.


## v0.18.9 authoritative progress and complete-only ledger

v0.18.9 removes checkmark-count inference from detached Amazon return HTML. DOM checkmarks must be structurally bound/non-hidden and cannot outrank affirmative Amazon lifecycle prose. The normal ledger now shows only fully processed orders; incomplete work is isolated in Processing and terminal order failures in Errors. Completed orders with real return-status links display authoritative return captures rather than provisional link records. Search now includes ASIN/card/status/order/product evidence, with status/year/card filters and multiple sort modes. Issue #29 tracks live acceptance.


## v0.18.10 dashboard metric cleanup

v0.18.10 removes the redundant `Order details` stat because complete orders are already fully processed canonical orders. The single `Complete orders` stat keeps the completed-order count plus captured-order-dollar total. Processing remains an internal crawler state and is no longer a user-facing tab/stat. User navigation is exactly `Orders | Returns | Return review | Errors`. Issue #31 tracks live acceptance.


## v0.18.11 replacement workflow separation

Amazon replacements are modeled independently from refund returns. Product-scoped Order Details evidence such as `Replacement requested`, `Replacement shipped`, `Replacement delivered`, and `Replacement complete` is retained on the purchased item. A replacement-management `/spr/returns/prep` link is excluded from return/refund processing only when the same product context affirmatively proves that no return is required. Replacement workflows without that proof remain return-eligible because some replacements require the original item back. Replacement-only orders do not count as Returns, do not show a synthetic `$0.00` refund, and expose replacement state in the order/product UI and status filter. Issue #33 tracks live acceptance.


## v0.18.12 adaptive smart-fast serial pacing

v0.18.12 speeds the default crawler without adding concurrency. Inter-job delay is 75–250 ms, normal bursts are 60–90 jobs with 8–15 second cooldowns, and Amazon throttle cooldown remains 10–20 minutes. Rendered worker pages no longer use a blind 450–900 ms settle delay: after Chrome reports navigation complete, the background worker polls a lightweight content-script readiness probe after 100–150 ms and every 75–125 ms for up to 700 ms. Detail/history/return readiness requires job-specific DOM evidence. A readiness timeout is not accepted as completeness; it falls through to the existing authoritative scan/retry/completeness gates. History lazy-load settling now requires both document height and visible Order-ID fingerprint to remain stable for three samples. The crawler remains one job at a time. Issue #35 tracks live throughput/rate-limit acceptance.


## v0.18.13 authoritative Reset & Refresh and dynamic version display

Separate Reset and Refresh controls are replaced by one `Reset & Refresh` recovery action. It preserves only the selected Order ID and captured real Order Details URL, removes all stored product/return/refund/replacement/bank/manual derived state, reopens the order as incomplete, and immediately rebuilds it from canonical Amazon evidence using the existing serial crawler lock. A failed rebuild remains in Errors with the real Details URL so retry remains possible. The dashboard header no longer hard-codes a historical version; it renders `chrome.runtime.getManifest().version_name || version` from the installed build. Issue #37 tracks live acceptance.


## v0.18.14 durable checkpoint resume and Amazon Auto-start

An active lifetime crawl now resumes from its persisted year/page/history URL and Order-ID checkpoint even if the MV3 worker, Chrome, or inactive Amazon worker tab disappears. An interrupted `currentJob` is requeued exactly once; an active empty queue is reconstructed from the saved checkpoint instead of starting current-year page 1. Visible duplicate Order IDs act as resume anchors: a completed overlap can be authoritatively refreshed once, but it is never counted as a new order or used to restart traversal.

`Auto-start: On/Off` is opt-in and defaults OFF. When enabled, loading an active user Amazon tab starts or resumes incomplete lifetime work in a separate inactive worker tab. Worker/inactive tabs cannot recursively trigger Auto-start, explicit Stop latches until manual Start/Resume or Restart, and a completed lifetime scan is not automatically restarted on every Amazon navigation.

v0.18.14 also replaces destructive development-version resets with migration-preserved ledger/crawl state. Version updates clear stale transient worker-tab identity but keep canonical orders, returns, bank verification, and the exact crawl checkpoint so the updater itself no longer destroys resume progress. Issue #39 tracks live acceptance.


## v0.18.15 newest-first scan sessions
Every newly started scanner session begins at the newest Amazon order (current year page 1), while the prior year/page checkpoint is retained as a historical frontier. The pass walks backward through every page, refreshes each already-complete Order ID exactly once in that session using its real canonical Order Details route, captures new/incomplete IDs normally, and continues beyond the prior frontier into older unscanned history. Known-order refreshes are non-destructive on ordinary failure and never increment the global unique-order count. A transient MV3 service-worker recovery inside the same running session still resumes its in-flight/checkpoint work so browser internals cannot force repeated page-1 rewinds. Issue #41 tracks live acceptance.

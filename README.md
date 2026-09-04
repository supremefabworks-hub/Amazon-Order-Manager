# Amazon Order Manager

Chrome Manifest V3 extension for building a local Amazon / Amazon Business order and refund ledger from the authenticated browser session.

**Current source baseline: v0.18.4 candidate for Issue #19.** GitHub is the source of truth and chat sessions are disposable.

Two issues remain intentionally separate:

- **#7 — live Amazon Business acceptance** for the authoritative v0.17 crawler/return behavior that remains unchanged in v0.18.
- **#10 — verified development auto-update pipeline** for the v0.18 local update workflow. Its code/test scope is implemented, but the one-time Windows bootstrap and one subsequent automatic update must be live-validated before the issue closes.

## Start a completely new chat

Use [`NEW_CHAT_PROMPT.md`](NEW_CHAT_PROMPT.md). `SESSION_PROTOCOL.md` defines mandatory startup/handoff behavior and `AGENTS.md` requires contributors to reconstruct state from GitHub rather than chat history.

## Resume development

1. Read `AGENTS.md`, `PROJECT_HANDOFF.md`, `README.md`, `TESTING.md`, and `SESSION_PROTOCOL.md`.
2. Read Issues #7 and #10 and any newer issue that supersedes either scope.
3. Inspect root source, `manifest.json`, recent commits, open PRs/issues, and tests before editing.
4. Root v0.18.4 is the active candidate for the terminal-cancelled-order live fix. The archived v0.16.0 ZIP is recovery material only.
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

This release is also the unattended updater proof from repaired v0.18.2. Do not manually replace `current` or press Reload when `dev-v0.18.3` publishes.

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

A later strictly newer release must update unattended from the repaired v0.18.2 installation before Issue #10 can close.

## Core v0.17/v0.18 product architecture

v0.18.1 does not loosen the v0.17 Amazon data contract. It additionally hardens payment-card last-four capture so generic Amazon layout `card` containers, gift-card values, and unrelated masked numbers cannot become canonical card evidence.

### Canonical orders

- Every visible history order must use its real Amazon `View order details` URL.
- The extension never synthesizes missing canonical detail URLs.
- A managed crawl stops if a visible Order ID lacks its real detail link.
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

### Per-order Refresh and dashboard

Every row uses the same fixed `Details | Credit | Reset | Refresh` action group. `Refresh` uses the stored real Order Details URL, opens an inactive Amazon tab, parses rendered canonical details, follows real same-order return-status links when present, saves fresh state, and closes the temporary tab.

Views remain `All orders`, `Returns`, and `Needs review`, with no horizontally scrollable order containers. Needs Review dollars equal the expected-refund sum for return records currently flagged for review.

### Development reset policy

During active development, changing the manifest version wipes ledger/crawl/worker/workflow/bank-verification state and stores the new version. This remains intentional for v0.18 testing and must be replaced with migrations before production persistence is expected.

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


## v0.18.4 terminal cancelled-order handling

Amazon can render a fully cancelled `$0.00` order in Order History without any `View order details` URL. v0.18.4 adds a narrow terminal-history exception: only a scoped history card proving the same Order ID, an exact `Cancelled`/`Canceled` state, an exact `$0.00` total, and no real Order Details link may satisfy the managed crawl page gate. It is saved with `historyTerminalComplete=true` / `historyTerminalState=cancelled`, remains `detailScanComplete=false`, counts toward lifetime unique-order completion, and renders as `Cancelled` / `Terminal history` with Details and Refresh disabled. Any normal, ambiguous, nonzero, or unknown-total missing-link order still hard-stops the crawler rather than inventing a URL.

Issue #19 tracks live acceptance using order `112-3886192-2097013` as the observed case. This release is also intended as the automatic updater test from a fresh v0.18.3 installation on the second Windows PC.

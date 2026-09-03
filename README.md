# Amazon Order Manager

Chrome Manifest V3 extension for building a local Amazon / Amazon Business order and refund ledger from the authenticated browser session.

**Current source baseline: v0.17.0.** The root source tree is complete. GitHub is the source of truth and chat sessions are disposable.

Issue **#7 — v0.17 authoritative details, return refresh, crawler and UI fixes** remains the active release tracker until the documented live Amazon Business acceptance pass is completed. The code/test scope of Issues #2–#7 is implemented in v0.17.0.

## Start a completely new chat

Use [`NEW_CHAT_PROMPT.md`](NEW_CHAT_PROMPT.md). `SESSION_PROTOCOL.md` defines mandatory startup/handoff behavior and `AGENTS.md` requires contributors to reconstruct state from GitHub rather than chat history.

## Resume development

1. Read `AGENTS.md`, `PROJECT_HANDOFF.md`, `README.md`, `TESTING.md`, and `SESSION_PROTOCOL.md`.
2. Read Issue #7 and any newer issue that supersedes it.
3. Inspect root source, `manifest.json`, recent commits, and tests before editing.
4. Root v0.17.0 is the active source. The archived v0.16.0 ZIP is recovery material only.
5. Run `npm test` before packaging or merging changes.
6. Keep implementation, regression tests, docs, issue state, and handoff synchronized.

## v0.17 architecture

### Canonical orders

- Every visible history order must use its real Amazon `View order details` URL.
- The extension no longer synthesizes missing canonical detail URLs.
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

The tested Amazon Business UI has used routes such as:

`#time/2026/pagination/1/` -> `#time/2026/pagination/2/` -> `#time/2026/pagination/3/`

### Returns

- `Return or replace items` alone is never evidence of a return.
- A real `/spr/returns/prep` link discovered from Order Details may be followed only for that same order as secondary lifecycle enrichment.
- Return stages are evidence-based and monotonic.
- A future credit date is an ETA, not a completed credit.
- Bundled/multi-item returns are stored as item-level records. Whole-order/whole-return totals are not duplicated onto each returned item.
- Multiple separate returns may exist under one Amazon Order ID.

### Payment card last four

- Card last four is extracted only from payment-method/payment-information evidence.
- DOM payment sections are preferred.
- A narrow text window beginning at a payment heading may be used if selectors are unavailable.
- Whole-page arbitrary four-digit text is not a fallback.

### Per-order Refresh

Every row has a fixed four-action group:

`Details | Credit | Reset | Refresh`

`Refresh` uses the stored real Order Details URL, opens an inactive Amazon tab, parses the rendered detail page, follows real return-status links for the same order when present, saves fresh state, and closes the temporary tab.

### Dashboard

- Views: `All orders`, `Returns`, `Needs review`.
- Same compact grid structure for every row/status.
- Inapplicable actions are disabled instead of removed.
- No horizontally scrollable order containers.
- Needs Review dollar total equals the expected-refund sum of the flagged return records.

### Development reset policy

During active development, changing the manifest version wipes ledger/crawl/worker/workflow/bank-verification state and stores the new version. v0.17 also handles upgrade from v0.16 even though v0.16 did not previously persist the version key.

Disable this destructive policy before a production release where data migration/persistence is expected.

## Validation

Run:

```bash
npm test
```

The suite covers parser, storage, background navigation, strict crawl state, reconciliation, and UI regressions. See `TESTING.md` and `PROJECT_HANDOFF.md` for the complete live acceptance checklist.

## Privacy / security

The extension must never receive bank credentials, financial-provider tokens, password/session exports, or full bank transaction feeds. Bank reconciliation remains the narrow JSON bridge documented in the repository.

Do not add CAPTCHA bypass, stealth/anti-detection behavior, cookie/password harvesting, or committed real-account Amazon/Teach Mode data.

## Recovery archive

The exact pre-GitHub v0.16.0 ZIP remains under `source-snapshots/v0.16.0/full/` for recovery/audit only.

Documented SHA-256:

`0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42`

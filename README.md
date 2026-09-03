# Amazon Order Manager

Chrome Manifest V3 extension for building a local Amazon / Amazon Business order and refund ledger from the authenticated browser session.

**Current baseline:** v0.16.0. This repository is the source of truth. A new development session should read `AGENTS.md` and `PROJECT_HANDOFF.md` before changing crawler, parser, return-state, card, or reconciliation logic.

## Resume development in a new chat

1. Open this repository and read `PROJECT_HANDOFF.md`.
2. Review open Issues #2–#6 for the v0.17 implementation backlog.
3. If the active source is incomplete, restore the exact v0.16.0 build from `source-snapshots/v0.16.0/` using its `RESTORE.md` instructions. The reconstructed ZIP must have SHA-256 `0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42` and size 77,670 bytes.
4. Expand the restored source into the repository root as tracked by Issue #1, then run `npm test`.
5. Continue as v0.17.0; during active development, version changes should wipe the local extension ledger/crawl state so each build starts clean.

## Development workflow

Clone this repository once, load the repository root with Chrome **Load unpacked**, then pull changes and click **Reload** in `chrome://extensions`. CI is configured to run the regression suite and package an installable ZIP once the full active source is present at the repository root.

## Current architecture

- Scan Amazon/Amazon Business order-history pages year by year.
- Finish every page in a year before switching to the next older year.
- Capture real `View order details` links; Order Details is the canonical order record.
- Use real return-status links only as secondary lifecycle enrichment for actual returns.
- Keep one canonical order record per Amazon Order ID with item-level return records.
- Reconcile issued refunds through a narrow import/export bridge so bank credentials never enter the extension.

## Important Amazon Business finding

The tested Amazon Business UI uses client-side history routes such as:

`#time/2026/pagination/1/` → `#time/2026/pagination/2/` → `#time/2026/pagination/3/`

Do not assume that `?timeFilter=year-YYYY&startIndex=N` will advance this UI; it has been observed to serve the first page again. A history page counts only after the visible Order-ID fingerprint changes.

See `PROJECT_HANDOFF.md` for the full implementation requirements, known bugs, privacy constraints, and acceptance tests.

# Amazon Order Manager

Chrome Manifest V3 extension for building a local Amazon / Amazon Business order and refund ledger from the authenticated browser session.

**Current baseline:** v0.16.0. This repository is the source of truth. Chat sessions are intentionally disposable; no development session should require access to an earlier chat.

## Start a completely new chat

Use the exact reusable prompt in [`NEW_CHAT_PROMPT.md`](NEW_CHAT_PROMPT.md). It instructs a fresh session to reconstruct all context from GitHub, inspect the active issue/source/tests, recover the verified snapshot if necessary, implement the next work, and write all new project state back to GitHub before the chat ends.

`SESSION_PROTOCOL.md` defines the mandatory startup and handoff process. `AGENTS.md` instructs AI/contributors not to depend on chat memory.

## Resume development

1. Read `AGENTS.md`, `SESSION_PROTOCOL.md`, and `PROJECT_HANDOFF.md`.
2. Read `README.md` and `TESTING.md`.
3. Use **Issue #7 — v0.17 authoritative details, return refresh, crawler and UI fixes** as the primary active implementation checklist unless a newer issue supersedes it.
4. Inspect current root source, manifest version, recent commits, and tests rather than assuming the repo state.
5. The exact pre-GitHub v0.16.0 extension ZIP is archived under `source-snapshots/v0.16.0/full/`. Reconstruct it using that directory's README if a known-good baseline is needed.
6. Snapshot integrity: SHA-256 `0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42`, size `77,670` bytes.
7. New development should keep ordinary editable source files at repository root and continue as v0.17.0.
8. During active development, version changes should wipe local extension ledger/crawl state so every build starts clean. Disable that destructive policy before a production release.

## Development workflow

Clone this repository once and load the repository root with Chrome **Load unpacked** once the active source tree is complete. Thereafter, pull changes and click **Reload** in `chrome://extensions`. CI is configured to run the regression suite and package an installable ZIP once the full active source is present at repository root.

Every coherent development session must commit implementation, regression tests, changed architecture/acceptance criteria, and issue state. Critical information must never live only in chat.

## Current architecture

- Scan Amazon/Amazon Business order history year by year.
- Finish every page in the current year before switching to the next older year.
- A page is accepted only when its visible Order-ID fingerprint differs from the prior page.
- Capture real **View order details** links; Order Details is the canonical order record.
- Use real `/spr/returns/prep` links only as secondary lifecycle enrichment for an actual return on that same Order ID.
- Keep one canonical order record per Amazon Order ID with item-level return information.
- Reconcile issued refunds through a narrow import/export bridge so bank credentials never enter the extension.

## Important Amazon Business finding

The tested Amazon Business UI uses client-side history routes such as:

`#time/2026/pagination/1/` → `#time/2026/pagination/2/` → `#time/2026/pagination/3/`

Do not assume that `?timeFilter=year-YYYY&startIndex=N` will advance this UI; it has been observed to serve the first page again. Prefer the actual numbered pager/Next control and verify a different Order-ID fingerprint before advancing crawler state.

## Immediate v0.17 priorities

- Scope payment-card last-four extraction to the actual payment-method section; never accept an arbitrary four-digit token.
- Make `Detailed` mean a complete successful Order Details parse.
- Add per-order **Refresh** using an inactive background Order Details tab.
- Refresh real return lifecycle status from the return-status link exposed by Order Details.
- Prevent false `Refund issued` classifications and preserve monotonic return state.
- Track the actual returned item and item-level expected refund for bundled orders.
- Standardize every ledger row to one compact symmetric grid; enlarge Details / Credit / Reset / Refresh and keep them side-by-side.
- Preserve exact year/page/order crawl checkpoints and treat overlapping Order IDs as overlap evidence, not duplicate orders.
- Finish all pages in one year before selecting the next older year.

See `PROJECT_HANDOFF.md` and Issue #7 before implementing the next build.

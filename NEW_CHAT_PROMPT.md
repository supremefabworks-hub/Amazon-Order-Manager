# New Chat Continuation Prompt

Copy/paste the prompt below into a completely fresh chat. No prior chat context should be required.

---

Open and use the GitHub repository `supremefabworks-hub/Amazon-Order-Manager` as the **only project source of truth** for this task.

This chat is disposable. Do **not** rely on memory or assumptions from any previous conversation. Reconstruct project context from GitHub before editing anything.

## Startup procedure

1. Read `AGENTS.md` completely.
2. Read `PROJECT_HANDOFF.md` completely.
3. Read `README.md` and `TESTING.md`.
4. Read `SESSION_PROTOCOL.md`.
5. Read GitHub Issue **#7 — v0.17 authoritative details, return refresh, crawler and UI fixes** and any newer open issues that supersede it.
6. Inspect the current root source tree and recent commits before making changes.
7. If the active root source is incomplete or inconsistent, recover the exact v0.16.0 baseline from `source-snapshots/v0.16.0/full/` using its README and verify SHA-256 `0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42` before using it.
8. Treat the repository and GitHub issues as authoritative if anything in this prompt becomes stale.

## Current product contract

This is a Chrome Manifest V3 Amazon / Amazon Business Order Manager and Refund Ledger.

The required crawler sequence is strict:

`newest year -> page 1 -> capture every order -> complete canonical Order Details for every order -> next page -> repeat until no more pages -> next older year`

Do not switch years while a valid next page exists. Do not count pagination as successful unless the visible Order-ID fingerprint changes. Repeated IDs/page content indicate failed pagination, not progress.

**Order Details is canonical.** Every order must use its real `View order details` URL. A real `/spr/returns/prep` link found from Order Details may be followed only as secondary return-lifecycle enrichment for that same Order ID/item.

Normal orders are not returns. `Return or replace items` availability alone must never create a return.

Return records must be item-level for bundled orders: show the actual returned product and the expected refund amount for that returned item/return record, never the full bundled order total as the expected refund.

Return lifecycle must be evidence-based. In-progress returns must not be labeled `Refund issued` without authoritative milestone evidence. Future credit dates are ETAs, not completed credits. Bank credit confirmation remains isolated from the extension through the narrow reconciliation bridge described in the repo.

The dashboard must stay compact, symmetric, systematic, and never use horizontally scrollable order containers. All order statuses use the same row/grid structure. `Detailed` means a complete successful canonical Order Details capture, not merely discovered/queued.

Each order needs a large side-by-side action group including `Details`, `Credit`, `Reset`, and `Refresh`. `Refresh` must force a fresh background/inactive Order Details tab scan for that order and refresh its real return status when applicable.

Payment card last-four parsing must be scoped to actual payment-method/payment-information evidence. Never use arbitrary four-digit page text.

During active development, a manifest version change should wipe extension ledger/crawl state so each version starts clean. This is a development policy and must be easy to disable before production.

## Implementation behavior

Work directly from the repository. Prefer concrete code changes over high-level advice. Preserve the security/privacy constraints in `AGENTS.md` and `PROJECT_HANDOFF.md`. Do not add CAPTCHA bypass, stealth/anti-detection behavior, password/cookie harvesting, or bank credentials to the extension.

Run the documented regression tests before packaging. Add regression tests for every bug fixed. For Amazon-specific behavior that cannot be proven from fixtures, keep diagnostics/checkpoints explicit rather than guessing.

When a coherent implementation pass is complete:

- bump the extension version,
- update source/tests/docs,
- update or close relevant GitHub issues,
- update `PROJECT_HANDOFF.md` if architecture, current baseline, known bugs, or acceptance criteria changed,
- commit everything needed to resume in another fresh chat,
- ensure no real Amazon exports, addresses, payment data, bank data, or Teach Mode logs are committed.

Do not leave important project state only in this chat. The repository must remain sufficient for the next chat to continue without this conversation.

Start by reporting what the repository says the current baseline is, the active issue/goal, whether the root source tree is complete, and the exact implementation plan. Then proceed with the work rather than asking me to restate prior context.

---

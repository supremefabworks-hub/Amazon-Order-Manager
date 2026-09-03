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
6. Inspect the current root source tree, manifest version, recent commits, open PRs/issues, and tests before making changes.
7. Treat the repository and GitHub issues as authoritative if anything in this prompt becomes stale.

## Current baseline

The complete root source baseline is **v0.17.0**. The exact v0.16.0 package under `source-snapshots/v0.16.0/full/` is historical recovery/audit material only and must not replace the complete v0.17 root unless an intentional rollback is explicitly required.

v0.17.0 implements the repository code/test scope for Issues #2–#7. The automated regression suite passes. Issue #7 remains open until the documented **live Amazon Business acceptance checklist** in `TESTING.md` is completed or any defects discovered by that live test are fixed.

## Current product contract

This is a Chrome Manifest V3 Amazon / Amazon Business Order Manager and Refund Ledger.

The required crawler sequence is strict:

`newest year -> page 1 -> capture every visible unique order -> complete canonical Order Details for every order -> next page -> repeat until no more pages -> next older year`

Do not switch years while a valid next page exists. Do not count pagination as successful unless the non-empty visible Order-ID fingerprint changes. Repeated IDs/page content are failed pagination, not progress. A URL/hash change alone is not progress.

**Order Details is canonical.** Every order must use its real `View order details` URL. Missing real detail links are a crawler stop condition; never synthesize a canonical Order Details URL.

`Detailed` means a complete matching Order Details capture containing order date, order total, and at least one item title.

A real `/spr/returns/prep` link found from Order Details may be followed only as secondary return-lifecycle enrichment for that same Amazon Order ID/item.

Normal orders are not returns. `Return or replace items` availability alone must never create a return.

Return records must be item-level for bundled orders: show the actual returned product and the expected refund amount for that returned item/return record, never the full bundled order total duplicated onto every returned item. Multiple separate returns under one Amazon Order ID must remain separate records.

Return lifecycle must be evidence-based. In-progress returns must not be labeled `Refund issued` without affirmative Amazon milestone evidence. Future credit dates are ETAs, not completed credits. Bank credit confirmation remains isolated from the extension through the narrow reconciliation bridge described in the repo.

Payment-card last-four parsing must be scoped to actual payment-method/payment-information evidence. Never use arbitrary four-digit page text.

The dashboard must stay compact, symmetric, systematic, and never use horizontally scrollable order containers. All rows use the same grid and the same fixed four actions: `Details`, `Credit`, `Reset`, `Refresh`. Inapplicable actions are disabled rather than removed.

`Refresh` must use the stored real Order Details URL, open an inactive/background Amazon detail tab, refresh the rendered canonical detail capture, follow real return-status links for the same order when present, save fresh state, and close the temporary tab.

During active development, a manifest version change wipes extension ledger/crawl state so each version starts clean. This is a development policy and must be disabled/replaced with migrations before production persistence is expected.

## Implementation behavior

Work directly from the repository. Prefer concrete code changes over high-level advice. Preserve the security/privacy constraints in `AGENTS.md` and `PROJECT_HANDOFF.md`. Do not add CAPTCHA bypass, stealth/anti-detection behavior, password/cookie harvesting, or bank credentials to the extension.

Run `npm test` before packaging. Add regression tests for every bug fixed. For Amazon-specific behavior that cannot be proven from fixtures, use the live acceptance checklist and explicit diagnostics/checkpoints rather than guessing.

When a coherent implementation pass is complete:

- bump the extension version if producing a new test build,
- update source/tests/docs,
- update or close relevant GitHub issues,
- update `PROJECT_HANDOFF.md` if architecture, current baseline, known bugs, live Amazon behavior, or acceptance criteria changed,
- commit everything needed to resume in another fresh chat,
- ensure no real Amazon exports, addresses, payment data, bank data, or Teach Mode logs are committed.

Do not leave important project state only in this chat. The repository must remain sufficient for the next chat to continue without this conversation.

Start by reporting the current baseline/version, active issue/goal, whether the root source tree is complete, and the exact plan. Then proceed with the work rather than asking me to restate prior context.

---

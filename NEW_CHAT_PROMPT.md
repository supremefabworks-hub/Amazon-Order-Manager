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
5. Read GitHub Issues **#7**, **#10**, **#13**, and **#15** plus any newer open issue that supersedes either scope.
6. Inspect the current root source tree, manifest/package version, recent commits, open PRs/issues, GitHub development releases, and tests before making changes.
7. Treat the repository and GitHub issues as authoritative if anything in this prompt becomes stale.

## Current baseline

The complete root source baseline is **v0.18.3 candidate for Issue #17**. The exact v0.16.0 package under `source-snapshots/v0.16.0/full/` is historical recovery/audit material only and must not replace the complete current root unless an intentional rollback is explicitly required.

v0.18 preserves the v0.17 authoritative Amazon behavior and adds the verified Windows development auto-update channel.

Two live-validation tracks remain separate:

- Issue #7 stays open until the documented live Amazon Business acceptance checklist in `TESTING.md` passes.
- Issue #10 stays open until the one-time Windows native-updater bootstrap and one subsequent real automatic update to a strictly newer version both pass.

## Development auto-update contract

The development extension uses a stable public manifest key and fixed extension ID:

`hhmimkpolikhncnbkkbbabbopbccabcf`

The fixed unpacked installation directory after one-time bootstrap is:

`%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\current`

The native host is:

`com.supremefabworks.amazon_order_manager_updater`

The extension checks for updates at Chrome startup and every 15 minutes. The native host considers only versioned GitHub prereleases tagged `dev-v<version>`, downloads `amazon-order-manager.zip` plus `amazon-order-manager.zip.sha256`, verifies the SHA-256 digest, embedded manifest version, and required files, stages the directory replacement, and reports success only after installation. The extension calls `chrome.runtime.reload()` only after a strictly newer successful install.

After bootstrap, do not manually overwrite the `current` folder. The updater owns it.

Every user-testable revision must bump **both** `manifest.json` and `package.json` to the same strictly newer Chrome version before merge. Main CI publishes the corresponding `dev-v<version>` prerelease only after tests pass. Do not overwrite an existing development release for another commit; bump the version instead.

The updater is development-only. Do not turn it into a remote-JavaScript loader. Do not place GitHub credentials, Amazon credentials/cookies, bank credentials/tokens, or private keys in the extension/updater. Before production, remove/disable the local updater, replace destructive development version resets with migrations, and use the Chrome Web Store update channel.


## v0.18.3 live acceptance additions

Accept captured Amazon legacy `/gp/css/summary/edit.html?orderID=...` as a real Order Details route, but never synthesize one. Missing-link stops must name the exact Order ID. Stable `returnItemId` binds a returned item; title variation alone is not a conflict, while contradictory non-empty ASIN evidence remains reviewable. Prefer trusted Order Details return-link item identity in the dashboard. Bare static `Refund issued` timeline labels are not affirmative status evidence. v0.18.3 is the unattended updater proof from repaired v0.18.2.

## v0.18.2 durable additions

Multiple returns under one Amazon Order ID must be modeled as `order -> return group -> returned item(s)`. Preserve Amazon return `rmaId`/`contractId` group identity and `itemId` child identity. Bind each return-status link to its nearest Order Details product block. Exact Order Details item binding is trusted; a conflicting later return-page identity must be flagged for review, not silently substituted.

Only the explicit standalone Order Details `Refund Total` is canonical for the order-level refund. Return/group amounts must be counted once, unknown refund money is `—`, and any child/group aggregate that exceeds the canonical refund is an integrity failure requiring review.

The prior v0.18.0 -> v0.18.1 automatic update failed in live Windows testing. v0.18.2 adds worker-start checks, observable popup updater status/manual check, synchronous reload after verified install, native-host file logging/self-test, and installer diagnostics. v0.18.2 requires one explicit Windows bootstrap repair. A later release must prove unattended update before Issue #10 closes.

## Amazon product contract

Required crawler sequence:

`newest year -> page 1 -> capture every visible unique order -> complete canonical Order Details for every order -> next page -> repeat until no more pages -> next older year`

Do not switch years while a valid next page exists. Do not count pagination as successful unless the non-empty visible Order-ID fingerprint changes. Repeated IDs/page content are failed pagination, not progress. A URL/hash change alone is not progress.

**Order Details is canonical.** Every order must use its real `View order details` URL. Missing real detail links are a crawler stop condition; never synthesize a canonical Order Details URL.

`Detailed` means a complete matching Order Details capture containing order date, order total, and at least one item title.

A real `/spr/returns/prep` link found from Order Details may be followed only as secondary return-lifecycle enrichment for that same Amazon Order ID/item.

Normal orders are not returns. `Return or replace items` availability alone must never create a return.

Return records must be item-level for bundled orders: show the actual returned product and the expected refund amount for that returned item/return record, never the full bundled order total duplicated onto every returned item. Multiple separate returns under one Amazon Order ID must remain separate records.

Return lifecycle must be evidence-based. In-progress returns must not be labeled `Refund issued` without affirmative Amazon milestone evidence. Future credit dates are ETAs, not completed credits. Bank credit confirmation remains isolated through the narrow reconciliation bridge described in the repo.

Payment-card last-four parsing must be scoped to actual payment-method/payment-information evidence. Never use arbitrary four-digit page text.
v0.18.1 specifically rejects generic Amazon DOM `card` containers, gift-card values, and unrelated masked values; only direct recognized card/payment/refund-method evidence may populate last-four.

The dashboard must stay compact, symmetric, systematic, and never use horizontally scrollable order containers. All rows use the same grid and fixed four actions: `Details`, `Credit`, `Reset`, `Refresh`. Inapplicable actions are disabled rather than removed.

`Refresh` must use the stored real Order Details URL, open an inactive/background Amazon detail tab, refresh the rendered canonical detail capture, follow real return-status links for the same order when present, save fresh state, and close the temporary tab.

During active development, a manifest version change wipes extension ledger/crawl state so each version starts clean. This must be disabled/replaced with migrations before production persistence is expected.

## Implementation behavior

Work directly from the repository. Prefer concrete code changes over high-level advice. Preserve the security/privacy constraints in `AGENTS.md` and `PROJECT_HANDOFF.md`. Do not add CAPTCHA bypass, stealth/anti-detection behavior, password/cookie harvesting, or bank credentials to the extension.

Run `npm test` before packaging. Add regression tests for every bug fixed. For Windows native-host behavior or Amazon behavior that cannot be proven from Linux fixtures, use the explicit live acceptance checklists rather than claiming it is validated.

When a coherent implementation pass is complete:

- bump manifest/package version if producing a new user-testable build,
- update source/tests/docs,
- update or close relevant GitHub issues,
- update `PROJECT_HANDOFF.md` if architecture, current baseline, known bugs, live findings, updater behavior, or acceptance criteria changed,
- commit everything needed to resume in another fresh chat,
- ensure no real Amazon exports, addresses, payment data, bank data, private keys, credentials, or Teach Mode logs are committed.

Do not leave important project state only in this chat. The repository must remain sufficient for the next chat to continue without this conversation.

Start by reporting the current baseline/version, active issues/goals, whether root source is complete, the current development release status, and the exact plan. Then proceed with the work rather than asking me to restate prior context.

---


### v0.18.5 terminal cancelled-order handling
Treat a scoped Order History card as terminal-complete without a Detail URL only when it proves the same Order ID, exact Cancelled/Canceled status, exact `$0.00` Total, and no real Detail link. Persist `historyTerminalComplete=true` / `historyTerminalState=cancelled`; never set `detailScanComplete` for this path. All other visible orders still require real captured Order Details URLs. Issue #19 tracks live acceptance.

- v0.18.5: no-detail Order History cards use structural single-order scoping; broad return-page product links cannot create ASIN conflicts unless identity evidence is directly item-bound.


### v0.18.6 durable addition
Amazon Order History year rollover is determined by scoped pager state. Disabled/no actionable Next on the selected final page ends the year; unrelated `Next` page text is ignored. Within-year progress still requires a changed visible Order-ID fingerprint. Issue #23 tracks live rollover acceptance.


### v0.18.7 durable addition
Return milestone completion is evidence-safe: static timeline labels, future instructions, and policy/hypothetical prose never complete a milestone. Canonical Order Details persists structured purchased `orderItems`; the dashboard stays one order card with per-product status/return lifecycles. Normal crawl pacing is ~30% faster by shorter serial waits only, with concurrency/rate-limit/fingerprint/canonical-detail safeguards unchanged. Issue #25 tracks live acceptance.


### v0.18.8 durable addition
Amazon return lifecycle and bank credit verification are independent. Render five Amazon stages including Return received. Future/static labels do not complete stages; milestone checkmarks are leading-stage evidence. Bank evidence never promotes Amazon stage; bank-before-refund-issued is a review conflict. Issue #27 tracks acceptance.

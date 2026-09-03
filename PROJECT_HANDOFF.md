# Project Handoff — Amazon Order Manager

## Purpose

Chrome Manifest V3 extension for scanning Amazon / Amazon Business order history, building one durable record per Order ID, tracking actual returns and refund progress, and reconciling Amazon-issued refunds against separately connected financial accounts without exposing bank credentials to the extension.

The repository is the source of truth. Current imported baseline: **v0.16.0**. The next implementation pass should be **v0.17.0** and should address the open issues below before adding unrelated features.

## Core product requirements

1. **Lifetime order crawl**
   - Scan newest year first.
   - For each year, process page 1, page 2, page 3, etc. until Amazon exposes no further page.
   - Only then switch to the next older year.
   - Preserve a persistent checkpoint so Stop/Resume continues from the exact year/page/order position.
   - Deduplicate globally by Amazon Order ID and record overlap rather than creating duplicate orders.

2. **Order Details are canonical**
   - Every order discovered from history must have its actual `View order details` URL captured.
   - Canonical URL shape currently observed on Amazon Business US: `https://www.amazon.com/your-orders/order-details?orderID=<ORDER_ID>&ref=ab_ppx_yo_dt_b_fed_order_details`.
   - Product title, order total, payment method/card, order status, order date, and item details should come from this page whenever available.
   - v0.16 fetches the real Order Details URL using authenticated same-origin `fetch(..., { credentials: "include" })` and parses the returned HTML with `DOMParser`. This design was adapted from Xenolphthalein/order-history-exporter-for-amazon.

3. **Return status is secondary enrichment, not the order source**
   - An Order Details page may contain a real return-status link like `/spr/returns/prep?...`.
   - Follow that URL only to refresh the return lifecycle for the same Order ID.
   - Do not use a generic `Return or replace items` link as proof that a return was started.
   - Do not replace the canonical Order Details record with a return page.

4. **Return lifecycle**
   - Desired milestones: `Initiated -> Dropped off / shipped -> Refund issued -> Bank credited`.
   - A future Amazon date such as `credited by Sep 7` is an ETA and must display as `Expected by Sep 7`, not a completed credit.
   - `Refund issued` must require strong evidence. Generic refund wording, a return-status link, or an expected amount must not promote an in-progress return to issued.
   - Status should not regress when a stale/less-specific page is scanned after a newer authoritative status.

5. **Bundled / multi-item orders**
   - Return records are item-level inside an order.
   - Always show the actual returned product(s), not the whole bundled order as the return subject.
   - Expected refund is the expected amount for that returned item/return record, not the order total.
   - An order may have multiple separate return records and amounts.

6. **Dashboard**
   - Primary filters: `All orders`, `Returns`, `Needs review`.
   - One consistent row/grid template for every order regardless of status.
   - No horizontally scrollable order containers at any viewport width.
   - Compact line-item layout so many orders are visible at once.
   - `Needs review` dollar total must equal the sum of expected refund amounts of the return records currently flagged Needs Review.
   - Large fixed action group, side by side: `Details`, `Credit`, `Reset`, plus `Refresh` after v0.17.
   - The `Detailed` badge should mean the complete Order Details refresh succeeded, not merely that an order was seen or queued.

7. **Per-order forced refresh**
   - Add a Refresh button next to every order.
   - User-requested behavior: force-open an inactive/background Amazon Order Details tab, parse fresh data for that one order, follow any existing return-status link for lifecycle refresh, save the result, then close/reuse the worker tab.
   - This is intentionally different from bulk same-origin fetch so there is a strong manual recovery path when fetched HTML differs from rendered Amazon state.

8. **Payment card parsing**
   - Known bug in v0.16: wrong last-four can be assigned because the parser can pick an unrelated 4-digit token from the page.
   - v0.17 must scope extraction to actual payment-method / payment-information DOM sections and require local semantic evidence such as `Visa ending in 1234`, `Mastercard ending in`, `Amex`, `payment method`, etc.
   - Do not use a naked `\b\d{4}\b` match across page text.

9. **Bank credit reconciliation**
   - The extension must never receive bank credentials, financial-connection tokens, or the full financial transaction feed.
   - Current secure bridge: extension exports narrow refund verification request JSON; ChatGPT can reconcile against separately connected financial accounts; user imports narrow verification result JSON.
   - Pending or ambiguous matches do not count as credited.

## Amazon Business navigation observed in Teach Mode

The tested account uses client-side hash routes when the visible year/pager is used:

- `#time/2026/pagination/1/`
- `#time/2026/pagination/2/`
- `#time/2026/pagination/3/`

The page also exposes a `timeFilterDropdown` containing year values such as `2026`, `2025`, `2024`, etc.

The upstream exporter commonly synthesizes `?timeFilter=year-YYYY&startIndex=10`, but that behavior was observed to re-serve page 1 in this Amazon Business UI. Therefore:

- Prefer the actual visible numeric pager / Next control and verify the Order-ID fingerprint changed.
- Do not count a new page merely because `location.href` changed.
- Do not switch year while a valid next page exists.
- If page IDs repeat, treat it as failed pagination/retry, not progress.

## Upstream implementation reviewed

Repository: `Xenolphthalein/order-history-exporter-for-amazon`

Useful patterns already adopted:

- Real Order Details URL detection: `a[href*="order-details"], a[href*="orderID="], a[href*="orderId="]`.
- Authenticated same-origin Order Details fetch with `credentials: "include"`.
- `DOMParser` parsing of fetched Order Details HTML.
- Product-title fallback chain: link text -> nearby title node -> title/aria-label -> image alt.
- One record per unique Order ID.

Not suitable as-is for this Amazon Business account: its `startIndex += 10` / `timeFilter=year-YYYY` page traversal.

Upstream is Unlicense/public domain.

## Current code structure

- `manifest.json` — MV3 manifest.
- `background.js` — worker queue, crawl state machine, tabs, alarms, throttling/backoff.
- `content.js` — Amazon-page integration, automatic page scan, UI injection.
- `parser.js` — order/history/detail/return parsing.
- `storage.js` — ledger model, merge semantics, status summaries, bank reconciliation import/export.
- `dashboard.html/js` + `ui.css` — full ledger UI.
- `popup.html/js` — compact extension menu/status.
- `workflow-recorder.js` — Teach Mode recorder used to capture live Amazon UI mechanics.
- `*-test.js` — Node regression tests.

## Required next changes (v0.17)

1. Fix payment last-four scoping.
2. Refresh return state by following real return-status link found on Order Details.
3. Prevent false `Refund issued` classification for returns still in progress.
4. Make `Detailed` mean a successful complete canonical detail capture.
5. Add per-order forced background-tab Refresh.
6. Map each return to the actual item(s) and item-level expected refund amount in bundled orders.
7. Make every dashboard row use the exact same column/grid structure.
8. Make Details / Credit / Reset / Refresh buttons approximately 3x current clickable size while staying side-by-side.
9. Keep processing all pages of a year; switch to older year only after end-of-year pagination is proven.
10. Add automatic clean-ledger reset on extension version change, because the current development preference is to wipe data for each version while iterating.

## Development reset policy

During active development, requested behavior is fresh data on every version bump:

- Store installed extension version in `chrome.storage.local`.
- On service-worker startup/install/update, compare with `chrome.runtime.getManifest().version`.
- When version differs, clear extension ledger/crawl state and seed defaults, then store the new version.
- Mark this as a development policy so it can be disabled before production releases where users expect migration.

## Testing acceptance criteria

Run:

- `node parser-test.js`
- `node storage-test.js`
- `node background-test.js`
- `node state-machine-test.js`
- `node reconciliation-test.js`

Live Amazon Business acceptance:

- History counter goes beyond page 1 while staying in the same year.
- Order IDs on page N differ from page N-1 before page N is accepted.
- Last page of year triggers next older year, not a loop.
- Every displayed `Detailed` order has a successful canonical Order Details parse.
- Wrong unrelated four-digit values never become card endings.
- A normal order with `Return or replace items` remains a normal order.
- A real existing return-status link creates/updates an item-level return record.
- Return in progress does not show Refund issued until authoritative evidence exists.
- Bundle order shows returned product + return amount for that product.
- Dashboard remains symmetric and has no side-scrolling order list.

## Privacy / security

Do not commit exported Amazon order history, Teach Mode logs from a real account, bank reconciliation request/result files, addresses, card numbers, or other user data. Keep fixtures synthetic.
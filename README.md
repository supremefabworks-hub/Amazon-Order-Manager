# Amazon Order Manager

Chrome Manifest V3 extension for building a local Amazon / Amazon Business order and refund ledger from the authenticated browser session.

**Current baseline:** v0.16.0. The repository is now the source of truth. Read `PROJECT_HANDOFF.md` before continuing development; it contains the live Amazon Business navigation findings, architecture decisions, known bugs, and the v0.17 acceptance criteria.

## Development workflow

Clone this repository once, load the repository root with Chrome **Load unpacked**, then pull changes and click **Reload** in `chrome://extensions`. GitHub Actions runs the regression suite and produces an installable ZIP artifact on every push.

## Current architecture

- Scan Amazon/Amazon Business order-history pages year by year.
- Capture real `View order details` links and fetch those authenticated pages locally.
- Keep one canonical order record per Amazon Order ID.
- Track item-level returns and refund milestones separately from normal orders.
- Reconcile issued refunds through a narrow import/export bridge so bank credentials never enter the extension.

## Important Amazon Business finding

The tested Amazon Business UI uses client-side history routes such as:

`#time/2026/pagination/1/` → `#time/2026/pagination/2/` → `#time/2026/pagination/3/`

Do not assume that `?timeFilter=year-YYYY&startIndex=N` will advance this UI; it has been observed to serve the first page again.

See `PROJECT_HANDOFF.md` for full implementation requirements and known issues.
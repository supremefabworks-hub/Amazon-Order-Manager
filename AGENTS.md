# AI / Contributor Instructions

Read `PROJECT_HANDOFF.md` before changing crawler, parser, return-state, payment-card, or reconciliation logic.

Principles:

- Order Details is the canonical source for an order.
- A real return-status link may be followed only as secondary lifecycle enrichment.
- Never infer a return merely from availability of `Return or replace items`.
- Never infer a payment-card last four from arbitrary four-digit text.
- Never mark `Refund issued` or `Bank credited` without affirmative evidence.
- Keep one canonical order object per Order ID and item-level return records underneath it.
- Preserve strict year -> page -> all details -> next page -> next year crawl semantics.
- Treat repeated Order-ID fingerprints as failed pagination, not new progress.
- Do not add stealth/CAPTCHA bypass behavior. Back off or pause on Amazon verification/rate limiting.
- Do not commit real order exports, addresses, bank data, or Teach Mode logs.
- Run all Node regression tests before packaging.
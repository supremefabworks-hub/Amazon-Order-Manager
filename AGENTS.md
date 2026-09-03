# AI / Contributor Instructions

This project uses **disposable chat sessions**. GitHub is the durable project memory. Do not assume any prior conversation context exists.

## Mandatory startup

Before changing code:

1. Read `PROJECT_HANDOFF.md` completely.
2. Read `SESSION_PROTOCOL.md`.
3. Read `README.md` and `TESTING.md`.
4. Read the active GitHub issue referenced by README/handoff (currently Issue #7 unless superseded).
5. Inspect the current source tree, manifest version, recent commits, and tests.
6. If root source is incomplete/inconsistent, recover the verified baseline from `source-snapshots/` rather than asking the user to reconstruct prior chat context.

Do not ask the user to repeat project history that is already captured in GitHub.

## Core principles

- Order Details is the canonical source for an order.
- A real return-status link may be followed only as secondary lifecycle enrichment.
- Never infer a return merely from availability of `Return or replace items`.
- Never infer a payment-card last four from arbitrary four-digit text.
- Never mark `Refund issued` or `Bank credited` without affirmative evidence.
- Keep one canonical order object per Order ID and item-level return records underneath it.
- Preserve strict year -> page -> all details -> next page -> next year crawl semantics.
- Treat repeated Order-ID fingerprints as failed pagination, not new progress.
- Do not add stealth/CAPTCHA bypass behavior. Back off or pause on Amazon verification/rate limiting.
- Do not commit real order exports, addresses, bank data, authentication/session data, or Teach Mode logs.
- Run all documented Node regression tests before packaging.

## Mandatory handoff

Before a development session ends, ensure all information required by the next fresh chat is committed to GitHub. Update source/tests, the relevant issue(s), and `PROJECT_HANDOFF.md` whenever baseline, architecture, known defects, live Amazon findings, or acceptance criteria change.

Critical project state must never exist only in chat.

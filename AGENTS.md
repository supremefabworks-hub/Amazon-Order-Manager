# AI / Contributor Instructions

This project uses **disposable chat sessions**. GitHub is the durable project memory. Do not assume any prior conversation context exists.

## Mandatory startup

Before changing code:

1. Read `PROJECT_HANDOFF.md` completely.
2. Read `SESSION_PROTOCOL.md`.
3. Read `README.md` and `TESTING.md`.
4. Read active GitHub Issues #7 and #10 unless newer issues supersede either scope.
5. Inspect the current source tree, manifest/package version, recent commits, open PRs, and tests.
6. If root source is incomplete/inconsistent, recover the verified baseline from `source-snapshots/` rather than asking the user to reconstruct prior chat context.

Do not ask the user to repeat project history already captured in GitHub.

## Core Amazon/data principles

- Order Details is the canonical source for an order.
- A real return-status link may be followed only as secondary lifecycle enrichment for the same order.
- Never infer a return merely from availability of `Return or replace items`.
- Never infer a payment-card last four from arbitrary four-digit text.
- Never mark `Refund issued` or `Bank credited` without affirmative evidence.
- Keep one canonical order object per Order ID and item-level return records underneath it.
- Preserve strict year -> page -> all details -> next page -> next year crawl semantics.
- Treat repeated Order-ID fingerprints as failed pagination, not new progress.
- Do not add stealth/CAPTCHA bypass behavior. Back off or pause on Amazon verification/rate limiting.
- Do not commit real order exports, addresses, bank data, authentication/session data, or Teach Mode logs.
- Run all documented Node regression tests before packaging.

## Development auto-update rules

The v0.18 development channel uses a fixed unpacked directory plus a verified Windows Native Messaging updater. Treat this as part of the release architecture, not an optional convenience script.

- Every **user-testable** development revision must bump `manifest.json` and `package.json` to the same strictly newer Chrome version.
- Do not hardcode the current release version in unrelated regression tests. Version alignment belongs in the centralized release/version invariants.
- Do not manually overwrite the installed `%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\current` directory; the updater owns it after bootstrap.
- Do not bypass the SHA-256 sidecar, embedded-manifest-version validation, required-file validation, or staged install/rollback behavior.
- Do not allow a native-host response to trigger `chrome.runtime.reload()` unless the reported installed version is strictly newer and the host reports success.
- Keep the native host restricted to the fixed development extension origin/ID.
- Never put GitHub credentials, Amazon credentials/cookies, bank credentials/tokens, private keys, or other secrets in the extension or native updater.
- Never turn the updater into a remote-JavaScript loader or other remote-code-execution path inside MV3.
- A main-branch build must pass CI before it becomes a `dev-v<version>` prerelease.
- If a `dev-v<version>` tag already belongs to a different commit, bump the version; do not overwrite that release.
- The development native updater and destructive version-reset policy must be removed/replaced appropriately before Chrome Web Store production distribution.

## Mandatory handoff

Before a development session ends, ensure all information required by the next fresh chat is committed to GitHub. Update source/tests, the relevant issue(s), and `PROJECT_HANDOFF.md` whenever baseline, architecture, known defects, live Amazon findings, updater behavior, or acceptance criteria change.

Critical project state must never exist only in chat.

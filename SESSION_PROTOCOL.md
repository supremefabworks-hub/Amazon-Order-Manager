# Disposable Chat Session Protocol

The project is designed so individual AI/chat sessions are disposable. GitHub, not chat history, is the durable project memory.

## Rule 1 — GitHub is authoritative

A new session must not assume it remembers prior discussion. Before editing:

1. Read `AGENTS.md`.
2. Read `PROJECT_HANDOFF.md`.
3. Read `README.md` and `TESTING.md`.
4. Read the active GitHub issue(s), starting with the issue named by README/handoff.
5. Inspect the current source tree, manifest version, recent commits, and tests.
6. If active source is incomplete, use the verified recovery snapshot documented under `source-snapshots/`.

If chat history conflicts with the repository, use the repository unless the user explicitly changes the requirement and that change is then written back to GitHub.

## Rule 2 — No uncommitted architectural knowledge

Anything needed to understand or continue the project must be represented in one of these durable locations:

- source code and comments where appropriate,
- regression tests,
- `PROJECT_HANDOFF.md`,
- `AGENTS.md`,
- README / testing docs,
- GitHub issues.

Do not rely on a future session knowing why a parser, state transition, crawler guard, or UI rule exists.

## Rule 3 — Every development session starts with a state audit

Before implementing, establish:

- current manifest/package version,
- current baseline branch/commit,
- whether the root source tree is complete,
- active open issue and acceptance criteria,
- tests currently available,
- known live-Amazon behavior versus inferred/fixture-only behavior.

Do not ask the user to repeat information already captured in GitHub.

## Rule 4 — Every coherent change gets durable evidence

For each bug/feature:

- change implementation,
- add/update regression tests,
- update docs when behavior/architecture changes,
- update the corresponding GitHub issue,
- bump version when producing a user-testable extension build.

Live Amazon findings that materially change crawler/parser logic must be added to `PROJECT_HANDOFF.md` or a dedicated issue before the session ends.

## Rule 5 — Session close checklist

Before ending a development session or intentionally moving to a new chat:

1. Commit/push all source needed for the next session.
2. Run/document the regression tests.
3. Update `PROJECT_HANDOFF.md` with the new baseline, architecture changes, unresolved defects, and next acceptance criteria.
4. Update/close GitHub issues so the backlog matches reality.
5. Ensure README points to the current active issue/build.
6. Verify recovery instructions still work if active source is incomplete.
7. Confirm no sensitive user data was committed.

A session is not considered handed off if critical information exists only in chat.

## Privacy boundary

Never commit real Amazon exports, real Order IDs used as private fixtures, shipping addresses, account-holder data, card numbers, bank transaction exports, reconciliation request/result files, authentication/session data, or Teach Mode logs from the user's account. Use synthetic fixtures.

## Recovery baseline

The pre-GitHub v0.16.0 extension is preserved under `source-snapshots/v0.16.0/full/` as Base64 parts with checksum instructions. That snapshot is archival recovery material, not the preferred active source layout.

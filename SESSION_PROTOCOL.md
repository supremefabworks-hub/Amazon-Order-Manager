# Disposable Chat Session Protocol

The project is designed so individual AI/chat sessions are disposable. GitHub, not chat history, is the durable project memory.

## Rule 1 — GitHub is authoritative

A new session must not assume it remembers prior discussion. Before editing:

1. Read `AGENTS.md`.
2. Read `PROJECT_HANDOFF.md`.
3. Read `README.md` and `TESTING.md`.
4. Read active GitHub Issues #7 and #10 plus any newer issue that supersedes either scope.
5. Inspect the current source tree, manifest/package version, recent commits, open PRs, current GitHub development release, and tests.
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

Do not rely on a future session knowing why a parser, state transition, crawler guard, updater verification step, release rule, or UI rule exists.

## Rule 3 — Every development session starts with a state audit

Before implementing, establish:

- current manifest/package version and whether they match,
- current baseline branch/commit,
- whether the root source tree is complete,
- active open issues and acceptance criteria,
- open PRs,
- latest development prerelease/tag and whether it matches the current merged version,
- tests currently available,
- known live-Amazon behavior versus inferred/fixture-only behavior,
- known Windows native-updater live-validation status.

Do not ask the user to repeat information already captured in GitHub.

## Rule 4 — Every coherent change gets durable evidence

For each bug/feature:

- change implementation,
- add/update regression tests,
- update docs when behavior/architecture changes,
- update the corresponding GitHub issue,
- bump **both** manifest/package versions to the same strictly newer value when producing a user-testable development build.

Do not hardcode the current release version in unrelated tests. Central release/version invariants own version parity.

For the v0.18+ development channel, a user-testable build is not complete merely because source was pushed. PR CI must pass; after merge, main CI must package the extension ZIP, SHA-256 sidecar, Windows updater ZIP, and publish the versioned `dev-v<version>` prerelease. Do not overwrite a development release that belongs to another commit; bump the version.

Live Amazon findings that materially change crawler/parser logic and Windows updater findings that materially change bootstrap/install/update behavior must be added to `PROJECT_HANDOFF.md` or a dedicated issue before the session ends.

## Rule 5 — Session close checklist

Before ending a development session or intentionally moving to a new chat:

1. Commit/push all source needed for the next session.
2. Run/document regression tests and PR CI.
3. If a user-testable build was merged, verify main CI and the matching GitHub development prerelease.
4. Update `PROJECT_HANDOFF.md` with the new baseline, architecture changes, unresolved defects, updater live status, and next acceptance criteria.
5. Update/close GitHub issues so the backlog matches reality.
6. Ensure README points to the current issues/build/update flow.
7. Verify recovery instructions still work if active source is incomplete.
8. Confirm no sensitive user data, credentials, tokens, private keys, or real account logs were committed.

A session is not considered handed off if critical information exists only in chat.

## Privacy boundary

Never commit real Amazon exports, real Order IDs used as private fixtures, shipping addresses, account-holder data, card numbers, bank transaction exports, reconciliation request/result files, authentication/session data, Teach Mode logs from the user's account, native-host credentials, or private signing keys. Use synthetic fixtures.

The development updater may download only the packaged extension/release verification assets described in the repository. It must not become a remote-code loader inside the extension.

## Recovery baseline

The pre-GitHub v0.16.0 extension is preserved under `source-snapshots/v0.16.0/full/` as Base64 parts with checksum instructions. That snapshot is archival recovery material, not the preferred active source layout.

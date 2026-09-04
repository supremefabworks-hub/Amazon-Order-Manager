from pathlib import Path

def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f'{label}: target not found')
    return text.replace(old, new, 1)

# README current policy cleanup.
p = Path('README.md')
s = p.read_text(encoding='utf-8')
if '- **#37 — v0.18.13 acceptance**' not in s:
    anchor = '- **#35 — v0.18.12 acceptance** for adaptive smart-fast serial crawl pacing and rate-limit safety.'
    s = replace_once(s, anchor, anchor + '\n- **#37 — v0.18.13 acceptance** for combined Reset & Refresh and live installed-version display.\n- **#39 — v0.18.14 acceptance** for durable checkpoint resume, ledger-backed overlap recovery, and opt-in Amazon Auto-start.', 'README trackers')
s = replace_once(s,
"""- Every visible history order must use its real Amazon `View order details` URL.
- The extension never synthesizes missing canonical detail URLs.
- A managed crawl stops if a visible Order ID lacks its real detail link.
""",
"""- Every normal visible history order must resolve to a real Amazon `View order details` URL.
- The extension never synthesizes missing canonical detail URLs.
- During resume/recovery, a previously captured real canonical Order Details URL may be reused for the same known Order ID if the current history card temporarily omits its action. This is stored Amazon evidence, not URL synthesis.
- A managed crawl stops if a normal visible Order ID has neither a current real detail link nor a previously captured real canonical Detail URL.
""",
'README canonical recovery')
s = replace_once(s,
"""### Per-order Refresh and dashboard

Every row uses the fixed `Details | Credit | Reset & Refresh` action group. `Reset & Refresh` clears all derived data for that Order ID while preserving only the real captured Order Details route, then rebuilds the order from Amazon; failures remain visible in Errors with the route preserved. `Refresh` uses the stored real Order Details URL, opens an inactive Amazon tab, parses rendered canonical details, follows real same-order return-status links when present, saves fresh state, and closes the temporary tab.

Completed-data views are `All orders`, `Returns`, and `Needs review`; incomplete work is isolated in `Processing` and terminal per-order failures in `Errors`. No order container may scroll horizontally. Needs Review dollars equal the expected-refund sum for return records currently flagged for review.

### Development reset policy

During active development, changing the manifest version wipes ledger/crawl/worker/workflow/bank-verification state and stores the new version. This remains intentional for v0.18 testing and must be replaced with migrations before production persistence is expected.
""",
"""### Per-order recovery and dashboard

Every row uses the fixed `Details | Credit | Reset & Refresh` action group. `Reset & Refresh` clears derived data for that Order ID while preserving only the real captured Order Details route, then rebuilds canonical Order Details and legitimate same-order return children in an inactive Amazon tab. Failures remain visible in Errors with the real route preserved, and the temporary tab is always closed before the serial worker lock is released.

User-facing completed-data views are exactly `Orders`, `Returns`, `Return review`, and `Errors`. Incomplete non-error orders remain internal/hidden until complete. No order container may scroll horizontally. Return review dollars equal the expected-refund sum for return records currently flagged for review.

### Development state migration policy

As of v0.18.14, development version updates preserve canonical ledger data, bank verification evidence, and the exact lifetime-crawl checkpoint. The updater may clear/close stale transient worker-tab identity, then resumes active unpaused work from the persisted current job/year/page/fingerprint. Earlier v0.18 builds intentionally used destructive version resets; that policy is superseded and must not be reintroduced.
""",
'README current recovery/state policy')
s = s.replace('renders as `Cancelled` / `Terminal history` with Details and Refresh disabled.', 'renders as `Cancelled` / `Terminal history` with Details and Reset & Refresh disabled.', 1)
p.write_text(s, encoding='utf-8')

# PROJECT_HANDOFF current baseline must not point to v0.18.3.
p = Path('PROJECT_HANDOFF.md')
s = p.read_text(encoding='utf-8')
s = replace_once(s,
"**Current source baseline: v0.18.3 candidate for Issue #17.** Root source remains the active development source. The exact pre-GitHub v0.16.0 archive under `source-snapshots/v0.16.0/full/` is historical recovery material only.",
"**Current source baseline: v0.18.14 candidate for Issue #39.** Root source remains the active development source. The exact pre-GitHub v0.16.0 archive under `source-snapshots/v0.16.0/full/` is historical recovery material only. Historical release sections below describe behavior at those versions; the newest v0.18.14 handoff section and current root code supersede older operational policies where they conflict.",
'HANDOFF current baseline')
p.write_text(s, encoding='utf-8')

# TESTING current live target.
p = Path('TESTING.md')
s = p.read_text(encoding='utf-8')
old = """**v0.18.3** is the current live-fix target for Issue #17. It preserves the v0.17 Amazon crawler/return contract, retains the verified local development auto-update channel, and fixes the live false payment-card last-four contamination found in v0.18.0.

Two independent live boundaries remain:

- Issue #7: live Amazon Business acceptance of crawler/details/returns/UI behavior.
- Issue #10: live Windows bootstrap plus one subsequent automatic development update.
"""
new = """**v0.18.14** is the current live target for Issue #39. It preserves the authoritative Amazon crawler/return/replacement contract and v0.18.12 smart-fast serial pacing while adding durable checkpoint resume, ledger-backed recovery for already-known Order IDs, opt-in Amazon Auto-start, and state-preserving development-version migration.

Current live boundaries include:

- Issue #39: interrupt/resume must continue from the saved current job/year/page instead of restarting page 1; ledger-known overlaps must refresh at most once and continue; Auto-start must use a separate inactive worker tab and respect manual Stop.
- Issue #7: broad live Amazon Business acceptance of crawler/details/returns/UI behavior.
- Issue #10 is closed after unattended updater proof; v0.18.14 must additionally prove that updater-driven version changes preserve the active ledger/crawl checkpoint.
"""
s = replace_once(s, old, new, 'TESTING current target')
p.write_text(s, encoding='utf-8')

# NEW_CHAT_PROMPT startup/current baseline and obsolete destructive-reset production note.
p = Path('NEW_CHAT_PROMPT.md')
s = p.read_text(encoding='utf-8')
s = replace_once(s,
'5. Read GitHub Issues **#7**, **#10**, **#13**, and **#15** plus any newer open issue that supersedes either scope.',
'5. Read current GitHub Issues **#7**, **#23**, **#29**, **#31**, **#33**, **#35**, **#37**, and **#39**, plus any newer issue that supersedes their scope. Issue #10 is closed updater history.',
'NEW_CHAT issue list')
s = replace_once(s,
'The complete root source baseline is **v0.18.3 candidate for Issue #17**. The exact v0.16.0 package under `source-snapshots/v0.16.0/full/` is historical recovery/audit material only and must not replace the complete current root unless an intentional rollback is explicitly required.',
'The complete root source baseline is **v0.18.14 candidate for Issue #39**. The exact v0.16.0 package under `source-snapshots/v0.16.0/full/` is historical recovery/audit material only and must not replace the complete current root unless an intentional rollback is explicitly required.',
'NEW_CHAT baseline')
old_tracks = """Two live-validation tracks remain separate:

- Issue #7 stays open until the documented live Amazon Business acceptance checklist in `TESTING.md` passes.
- Issue #10 stays open until the one-time Windows native-updater bootstrap and one subsequent real automatic update to a strictly newer version both pass.
"""
new_tracks = """Current live validation is centered on Issue #39 (durable checkpoint resume / Auto-start / state-preserving upgrade) while Issue #7 remains the broad Amazon Business acceptance tracker. Updater Issue #10 is closed after unattended update proof.
"""
s = replace_once(s, old_tracks, new_tracks, 'NEW_CHAT live tracks')
s = s.replace('Before production, remove/disable the local updater, replace destructive development version resets with migrations, and use the Chrome Web Store update channel.', 'Before production, remove/disable the local updater, retain explicit tested storage migrations for schema changes, and use the Chrome Web Store update channel.', 1)
p.write_text(s, encoding='utf-8')

print('v0.18.14 source-of-truth docs finalized')
